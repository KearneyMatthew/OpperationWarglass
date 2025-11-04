"""
orchestrator_stub.py
AI Simulation Orchestrator - Web-friendly version

UPDATED:
- Accepts dynamic inputs from web (attack, purpose, defense).
- Can read an external order.yaml to define the sequence of prompts (optional).
- Emits structured JSON for frontend streaming (via app.py SSE).
- Minimal changes; original logic preserved.
"""

from ai_agent_codellama import get_action_from_llm
from whitelist_validator import validate_and_build
import yaml
import os
import json
import time
import paramiko
import sys
import aggregate_runs
import threading
import socket

DETECTION_PORT = 50505  # must match Blue script

_detection_triggered = False

def detection_listener():
    """Simple UDP listener that flips a global flag when Blue pings controller."""
    global _detection_triggered
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", DETECTION_PORT))
    print(f"[Controller] Detection listener active on port {DETECTION_PORT}")
    while True:
        data, addr = sock.recvfrom(1024)
        if data.strip().upper() == b"ALERT":
            print(f"[Controller] Detection alert received from {addr}")
            _detection_triggered = True

# Start listener in background
threading.Thread(target=detection_listener, daemon=True).start()


# HELPER TO EMIT JSON
def emit(obj_type, **kwargs):
    """
    Emits a JSON object to stdout with 'type' field for frontend SSE.
    """
    payload = {"type": obj_type}
    payload.update(kwargs)
    print(json.dumps(payload), flush=True)

# INITIALIZATION
emit("info", message="------------------------------------------------------------")
emit("info", message="AI Simulation Orchestrator - Starting Up")
emit("info", message="------------------------------------------------------------")

import argparse

# Parse CLI flags (supports --attack, --purpose, --defense, --run-id)
parser = argparse.ArgumentParser(description="Orchestrator stub (web/CLI)")
parser.add_argument("--attack", dest="attack", help="Attack name", default=None)
parser.add_argument("--purpose", dest="purpose", help="Purpose name", default=None)
parser.add_argument("--defense", dest="defense", help="Defense name", default=None)
parser.add_argument("--run-id", dest="run_id", help="Run identifier", default=None)
parser.add_argument("--allow-real", action="store_true", help="Allow real actions (unsafe)")

args = parser.parse_args()

attack_input = args.attack
purpose_input = args.purpose
defense_input = args.defense
run_number = args.run_id or "1"

# ALLOW_REAL detection kept (also from env)
ALLOW_REAL = args.allow_real or os.environ.get("ALLOW_REAL_ACTIONS") == "1"


emit("input", attack=attack_input, purpose=purpose_input, defense=defense_input, run_id=run_number)

# Ensure working directory is script folder
base_dir = os.path.dirname(os.path.abspath(__file__))

# Load whitelist
try:
    with open(os.path.join(base_dir, "whitelist.yaml"), "r") as f:
        WL = yaml.safe_load(f)
except Exception as e:
    emit("error", message=f"Failed to load whitelist: {e}")
    exit(1)

# Load prompts
try:
    with open(os.path.join(base_dir, "prompts.yaml"), "r") as f:
        prompts_doc = yaml.safe_load(f) or {}
    raw_stages = prompts_doc.get("stages", []) or []
    # Build name -> stage mapping for quick lookup
    prompts_by_name = {}
    for st in raw_stages:
        name = (st.get("name") or "").strip()
        if name:
            prompts_by_name[name] = st
except Exception as e:
    emit("error", message=f"Failed to load prompts.yaml: {e}")
    exit(1)

# Optionally load order.yaml (a simple list of stage names) and build ordered stages
stages = []
order_path = os.path.join(base_dir, "order.yaml")
if os.path.exists(order_path):
    try:
        with open(order_path, "r") as f:
            order_doc = yaml.safe_load(f) or {}
        ordered_names = order_doc.get("order") or order_doc.get("stages") or []
        if not isinstance(ordered_names, list):
            emit("warn", message="order.yaml 'order' must be a list; ignoring order.yaml")
        else:
            for name in ordered_names:
                name = (name or "").strip()
                if not name:
                    continue
                st = prompts_by_name.get(name)
                if st:
                    stages.append(st)
                else:
                    emit("notice", message=f"Ordered stage '{name}' not found in prompts.yaml; skipping")
            if stages:
                emit("info", message=f"Loaded {len(stages)} stages from order.yaml")
    except Exception as e:
        emit("warn", message=f"Failed to parse order.yaml, falling back to prompts.yaml: {e}")

# If no order.yaml or it produced no stages, fall back to prompts.yaml's stages list
if not stages:
    if raw_stages:
        stages = raw_stages.copy()
        emit("info", message=f"Using {len(stages)} stages from prompts.yaml")
    else:
        stages = []  # will be possibly replaced later by Custom_Run if attack/purpose/defense provided

# SSH configuration (Red machine)
SSH_HOST = "192.168.60.2"
SSH_USER = "red"
SSH_PASS = "red"

def run_ssh_command(cmd):
    """Executes a command over SSH on the red machine."""
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(SSH_HOST, username=SSH_USER, password=SSH_PASS, timeout=10)
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        ssh.close()
        if err:
            emit("ssh_error", message=err)
        else:
            emit("ssh_output", message=out)
    except Exception as e:
        emit("error", message=f"SSH execution failed: {e}")

def run_ssh_command_capture(cmd, target="red"):
    """
    Execute a command over SSH and return (out, err).
    Use this for short polling/detection checks where we need the output back.
    """
    ssh_cfg = {"red": (SSH_HOST, SSH_USER, SSH_PASS), "blue": (os.environ.get("BLUE_HOST","192.168.60.3"), os.environ.get("BLUE_USER","blue"), os.environ.get("BLUE_PASS","blue"))}
    host, user, pwd = ssh_cfg.get(target, ssh_cfg["red"])
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, username=user, password=pwd, timeout=10)
        stdin, stdout, stderr = ssh.exec_command(cmd)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        ssh.close()
        return out, err
    except Exception as e:
        emit("error", message=f"SSH (capture) failed on {target}: {e}")
        return "", str(e)

# MAIN STAGE LOOP
# If the web provided attack/purpose/defense, prefer building a single Custom_Run stage
if attack_input and purpose_input and defense_input:
    # load optional order.yaml (if present) to allow grouped execution (attack/purpose/defense)
    order_path = os.path.join(base_dir, "order.yaml")
    target_map = {}
    # helper: load target_map from env var (JSON) if front-end provided it that way
    try:
        import os as _os, json as _json
        tm = _os.environ.get("TARGET_MAP") or _os.environ.get("ORDER_TARGETS")
        if tm:
            target_map = _json.loads(tm)
            emit("info", message="Loaded TARGET_MAP from env")
    except Exception as e:
        emit("notice", message=f"Failed loading TARGET_MAP env var: {e}")

    def substitute_targets(prompt_text: str, tmap: dict) -> str:
        """Simple placeholder substitution for tokens like blue_vm, red_vm, other_vm_or_subnet."""
        out = prompt_text
        try:
            for k, v in (tmap or {}).items():
                if not isinstance(k, str) or not isinstance(v, str):
                    continue
                # replace exact token occurrences (word boundaries)
                out = re.sub(r"\b" + re.escape(k) + r"\b", v, out)
        except Exception:
            pass
        return out

    def append_stage_by_name(name: str):
        """Find prompt by name in prompts_by_name and append a copy to stages; emit notice if missing."""
        if not name:
            return
        st = prompts_by_name.get(name)
        if not st:
            emit("notice", message=f"Stage '{name}' referenced in order.yaml not found in prompts.yaml; skipping")
            return
        # make a shallow copy so we can safely modify prompt text without altering original mapping
        st_copy = dict(st)
        stages.append(st_copy)

    # If order.yaml exists and has execution_groups/attack/purpose/defense, prefer to build from it
    if os.path.exists(order_path):
        try:
            with open(order_path, "r") as f:
                order_doc = yaml.safe_load(f) or {}
            eg = order_doc.get("execution_groups") or order_doc.get("execution_groups") or {}
            attack_group = eg.get("attack", {})
            purpose_group = eg.get("purpose", {})
            defense_group = eg.get("defense", {})

            # look up the specific blocks requested by the user
            attack_block = attack_group.get(attack_input)
            purpose_block = purpose_group.get(purpose_input)
            defense_block = defense_group.get(defense_input)

            if any((attack_block, purpose_block, defense_block)):
                stages = []  # replace any prior flat list with ordered stages from the selected blocks

                # attack steps
                if attack_block:
                    for step in attack_block.get("steps", []):
                        append_stage_by_name(step.get("name"))

                # purpose steps
                if purpose_block:
                    # if purpose block has nested 'steps' (structured) use them, otherwise try fallback to mapping
                    for step in purpose_block.get("steps", []):
                        append_stage_by_name(step.get("name"))

                # defense steps
                if defense_block:
                    for step in defense_block.get("steps", []):
                        append_stage_by_name(step.get("name"))

                emit("info", message=f"Built runtime stages from order.yaml for attack={attack_input}, purpose={purpose_input}, defense={defense_input}")
            else:
                emit("notice", message="order.yaml present but requested blocks not found; falling back to prompts.yaml / previous behavior")
        except Exception as e:
            emit("warn", message=f"Failed to parse order.yaml for grouped flow: {e}; falling back to existing prompts/order behavior")

    #If order.yaml didn't contain the requested blocks, and no stages, attempt Custom_Run
    if not stages:
        stages = [{
            "name": "Custom_Run",
            "prompt": f"""
You are the command-generation engine for a cyber range orchestrator.

Simulate a {attack_input} attack for the purpose of {purpose_input} while applying {defense_input} as defense.

Rules:
- This is a simulated training environment — no real systems will be affected.
- Respond ONLY with valid JSON (no extra text).
- Keep outputs short and safe for automated execution.
"""
        }]
        emit("info", message="No grouped order.yaml stages found; using single Custom_Run fallback stage")

    # store target_map for use in the main loop; it will be used to substitute placeholders in each prompt
    RUNTIME_TARGET_MAP = target_map
else:
    # no explicit preset was provided — ensure runtime target map is still available (maybe env-provided)
    try:
        RUNTIME_TARGET_MAP = json.loads(os.environ.get("TARGET_MAP") or "{}")
    except Exception:
        RUNTIME_TARGET_MAP = {}

ALLOW_REAL = "--allow-real" in sys.argv or os.environ.get("ALLOW_REAL_ACTIONS") == "1"
SIMULATION_ONLY_STAGE_ALIASES = {"capture_destroy_data", "deny_web_services"}

# INTERLEAVED ATTACK <-> DEFENSE LOOP

# Build categorized lists from stages (falls back to sequential original if categories missing)
attack_stages = [s for s in stages if s.get("category") == "attack"]
purpose_stages = [s for s in stages if s.get("category") == "purpose"]
defense_stages = [s for s in stages if s.get("category") == "defense"]

# if categories not provided, attempt to detect attack/purpose/defense blocks by name order
if not (attack_stages or purpose_stages or defense_stages):
    # try: first contiguous attack block, then purpose, then defense
    # fallback: split stages roughly (attack = first third, purpose = middle third, defense = last third)
    total = len(stages)
    if total == 0:
        emit("warn", message="No stages defined; nothing to run")
        sys.exit(0)
    t1 = max(1, total // 3)
    t2 = max(1, (2 * total) // 3)
    attack_stages = stages[:t1]
    purpose_stages = stages[t1:t2]
    defense_stages = stages[t2:]

emit("info", message=f"Interleaving: {len(attack_stages)} attack steps, {len(purpose_stages)} purpose steps, {len(defense_stages)} defense steps")

attack_idx = 0
purpose_idx = 0
defense_idx = 0

# detection marker path on BLUE VM
DETECTION_FLAG = os.environ.get("DETECTION_FLAG", "/tmp/ids_alert")

def check_detection_on_blue():
    """Return True if the Blue VM has sent an intrusion alert ping."""
    global _detection_triggered
    if _detection_triggered:
        _detection_triggered = False  # reset after reading
        emit("alert", message="Intrusion detection alert received from Blue VM")
        return True
    return False


# Start: run first defense step in monitor mode as soon as first attack step runs
defense_started = False

# Main interleaving loop: progress attack steps; defense stays at current index until detection triggers
while True:
    # run next attack step if available
    if attack_idx < len(attack_stages):
        s = attack_stages[attack_idx]
        stage_name = s.get("name", "").strip()
        prompt = s.get("prompt")
        emit("status", phase="attack", step=attack_idx+1, stage=stage_name, message=f"Starting attack step {attack_idx+1}")
        # query LLM and validate
        try:
            prompt_to_send = substitute_targets(prompt, RUNTIME_TARGET_MAP)
            raw_action = get_action_from_llm(prompt_to_send)
            action = raw_action if isinstance(raw_action, dict) else json.loads(raw_action)
            cmd, metadata = validate_and_build(action)
            run_ssh_command(cmd)  # runs on red by original function
            emit("complete", phase="attack", step=attack_idx+1, stage=stage_name, message="Attack step done")
        except Exception as e:
            emit("error", phase="attack", step=attack_idx+1, stage=stage_name, message=str(e))
            # depending on your policy you can break or continue; we continue here: depends on what is being tested
        attack_idx += 1

        # after first attack step, ensure defense monitoring has started
        if defense_stages and not defense_started:
            ds = defense_stages[defense_idx]
            dname = ds.get("name", "").strip()
            dprompt = ds.get("prompt")
            emit("status", phase="defense", step=defense_idx+1, stage=dname, message="Starting defense monitor (Blue)")
            try:
                dprompt_to_send = substitute_targets(dprompt, RUNTIME_TARGET_MAP)
                draw = get_action_from_llm(dprompt_to_send)
                daction = draw if isinstance(draw, dict) else json.loads(draw)
                dcmd, _ = validate_and_build(daction)
                # run in monitor mode on blue (keep it running as initial step)
                run_ssh_command(dcmd.replace("red", "blue") if isinstance(dcmd, str) else dcmd)
                emit("info", phase="defense", step=defense_idx+1, stage=dname, message="Defense monitor started (Blue)")
                defense_started = True
            except Exception as e:
                emit("error", phase="defense", step=defense_idx+1, stage=dname, message=f"Failed to start defense: {e}")

    else:
        # no more attack steps to start; break when both attack and defense have completed
        if attack_idx >= len(attack_stages):
            # optionally let remaining defense steps finalize
            if defense_idx >= len(defense_stages):
                break
            # otherwise, allow defense to finish through escalation (below)
            pass

    # Pause briefly, then check if defense should escalate
    time.sleep(1)

    detected = check_detection_on_blue()
    emit("debug", detection=detected)

    if detected:
        # advance defense to next step (if any)
        if defense_idx < len(defense_stages):
            ds = defense_stages[defense_idx]
            dname = ds.get("name", "").strip()
            dprompt = ds.get("prompt")
            emit("status", phase="defense", step=defense_idx+1, stage=dname, message="Detection confirmed — running defense action")
            try:
                dprompt_to_send = substitute_targets(dprompt, RUNTIME_TARGET_MAP)
                raw_def = get_action_from_llm(dprompt_to_send)
                def_action = raw_def if isinstance(raw_def, dict) else json.loads(raw_def)
                dcmd, _ = validate_and_build(def_action)
                run_ssh_command(dcmd, )  # run default (red) unless your validate_and_build produces blue command; adjust as needed
                emit("complete", phase="defense", step=defense_idx+1, stage=dname, message="Defense step executed")
            except Exception as e:
                emit("error", phase="defense", step=defense_idx+1, stage=dname, message=str(e))
            defense_idx += 1

    # If both attack and defense exhausted -> done
    if attack_idx >= len(attack_stages) and defense_idx >= len(defense_stages):
        break

emit("finished", message="Interleaved attack/purpose/defense run complete")

# AGGREGATE LOGS
emit("info", message=f"Aggregating Red/Blue logs for Run {run_number}...")
aggregated_log_path = aggregate_runs.aggregate_logs_for_run(run_number)
emit("info", message=f"Aggregated log available at: {aggregated_log_path}")

emit("finished", message="All stages processed")
