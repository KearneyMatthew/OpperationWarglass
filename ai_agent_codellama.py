"""
ai_agent_codellama.py

CodeLlama interface using Ollama extracts JSON from AI outputs even if extra text is there(AKA IT WILL BE).
"""

import subprocess
import json
import re

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
    Calls local CodeLlama via Ollama CLI and return parsed JSON as a Python dict.
    This should also handle extra text, line breaks, or explanation from the AI.
    """
    try:
        result = subprocess.run(
            ["ollama", "run", MODEL_NAME, prompt],
            capture_output=True,
            text=True,
            check=True,
            timeout=120
        )
        output = result.stdout.strip()
        print(f"[DEBUG] LLM raw output:\n{output}")

        # Extract first JSON object
        json_str = extract_first_json(output).strip()

        # Try parsing JSON
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Repair initial parse if/when it fails
            repaired = _conservative_repair_text(json_str)
            try:
                parsed = json.loads(repaired)
                print("[DEBUG] Parsed JSON after repair.")
                return parsed
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    f"Invalid JSON returned by LLM.\nRaw:\n{json_str}\n\n"
                    f"Repaired:\n{repaired}\n\nError: {e}"
                )

    except subprocess.TimeoutExpired:
        raise RuntimeError("CodeLlama call timed out.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error calling CodeLlama: {e.stderr}") from e
    except ValueError as e:
        raise RuntimeError(f"Failed to extract JSON from LLM output:\n{output}\n{str(e)}") from e


#
# Test
#
if __name__ == "__main__":
    test_prompt = 'Return only JSON: {"tool": "ping", "params": {"target": "192.168.100.2"}}'
    action = get_action_from_llm(test_prompt)
    print("Parsed action:", action)
