"""
ai_agent_codellama.py

CodeLlama interface using Ollama extracts JSON from AI outputs even if extra text is there(AKA IT WILL BE).
"""

import subprocess
import json
import re
import os

MODEL_NAME = "codellama:7b-instruct"


#
# JSON extraction and repair
#

def _find_first_balanced(s: str, open_ch='{', close_ch='}') -> str | None:
    """Return substring from first open_ch to matching close_ch"""
    stack = []
    start = None
    for i, c in enumerate(s):
        if c == open_ch:
            if start is None:
                start = i
            stack.append(c)
        elif c == close_ch:
            if stack:
                stack.pop()
            if not stack and start is not None:
                return s[start:i+1]
    return None


def _conservative_repair_text(s: str) -> str:
    """Apply conservative repairs that commonly appear in Codellama output."""
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")

    # Drop leading labels
    s = re.sub(r"(?i)\baction:\s*", "", s)
    s = re.sub(r"(?i)\bjson:\s*", "", s)

    # Fix comma-separated IPs (e.g., 192,168,0,1 → 192.168.0.1) (HAPPENS OFTEN, it really likes commas and not periods)
    s = re.sub(r"\b(\d{1,3}),(\d{1,3}),(\d{1,3}),(\d{1,3})\b",
               lambda m: ".".join(m.groups()), s)

    # Convert single quotes to double quotes
    if re.search(r'["\']\w+["\']\s*:', s) or re.search(r'\{\s*["\']', s):
        s = re.sub(r"(?<!\w)'(?!\w)", '"', s)
        s = s.replace("':", '":').replace(":'", ':"').replace("',", '",').replace(",'", ',"')

    # Remove trailing commas
    s = re.sub(r",\s*([}\]])", r"\1", s)

    return s


def extract_first_json(output: str) -> str:
    """Extract first JSON-like block and repair common Codellama mistakes."""
    if not isinstance(output, str):
        raise ValueError("Output must be a string")

    # Try balanced object first
    candidate = _find_first_balanced(output, "{", "}")
    if candidate:
        return candidate

    # Try balanced array
    candidate = _find_first_balanced(output, "[", "]")
    if candidate:
        return candidate

    # Try again
    repaired = _conservative_repair_text(output)
    candidate = _find_first_balanced(repaired, "{", "}") or _find_first_balanced(repaired, "[", "]")
    if candidate:
        return candidate

    # last resort
    m = re.search(r"\{.*\}", repaired, flags=re.DOTALL)
    if m:
        return m.group(0)

    raise ValueError("No balanced JSON found (after repairs).")


#
# Main Codellama interface
#

def get_action_from_llm(prompt: str) -> dict:
    """
    More robust wrapper to call Ollama / CodeLlama.
    Uses Popen + communicate so we can kill the child cleanly and capture partial output on timeout.
    Timeout controlled by LLM_TIMEOUT env var (seconds), default 200.
    """
    LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "200"))

    # Build the command exactly as before; keep same CLI form to minimize change risk.
    cmd = ["ollama", "run", MODEL_NAME, prompt]

    try:
        # Start process
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        try:
            stdout, stderr = proc.communicate(timeout=LLM_TIMEOUT)
        except subprocess.TimeoutExpired:
            # Kill and capture any partial output for debugging
            try:
                proc.kill()
            except Exception:
                pass
            stdout, stderr = proc.communicate(timeout=5)
            # Provide partial output for diagnosis
            raise RuntimeError(f"CodeLlama call timed out (after {LLM_TIMEOUT}s). Partial stdout:\n{stdout}\n\nPartial stderr:\n{stderr}")

        # If process returned non-zero, surface stderr
        if proc.returncode != 0:
            raise RuntimeError(f"Error calling CodeLlama: returncode={proc.returncode}\nstderr:\n{stderr}")

        output = (stdout or "").strip()
        # Debug info (keeps your previous debug print)
        print(f"[DEBUG] LLM raw output:\n{output}")

        # Extract first JSON object (reuse your helper)
        json_str = extract_first_json(output).strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            repaired = _conservative_repair_text(json_str)
            try:
                parsed = json.loads(repaired)
                print("[DEBUG] Parsed JSON after repair.")
                return parsed
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    f"Invalid JSON returned by LLM.\nRaw:\n{json_str}\n\nRepaired:\n{repaired}\n\nError: {e}\n\nFull stdout:\n{stdout}\n\nFull stderr:\n{stderr}"
                )

    except RuntimeError:
        # re-raise RuntimeErrors (timeouts, bad return codes, JSON errors)
        raise
    except Exception as e:
        # Catch-all (unexpected errors)
        raise RuntimeError(f"Unexpected error calling CodeLlama: {e}") from e


#
# Test
#
if __name__ == "__main__":
    test_prompt = 'Return only JSON: {"tool": "ping", "params": {"target": "192.168.100.2"}}'
    action = get_action_from_llm(test_prompt)
    print("Parsed action:", action)
