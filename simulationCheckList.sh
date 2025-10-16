#!/bin/bash
# ======================================================
# tester.sh
# ------------------------------------------------------
# Comprehensive Pre-Test Script
#  - Loads IPs, users, passwords from red_vs_blue_config.yaml
#  - Validates required files
#  - Runs AI whitelist validation tests
#  - SSH connectivity check (controller -> red/blue)
#  - AI-generated ping test (red -> blue)
# ======================================================

set -euo pipefail

# Activate Python venv if exists
if [ -d "venv" ]; then
    echo "[INFO] Activating virtual environment..."
    source venv/bin/activate
else
    echo "[WARN] venv not found — using system Python"
fi

PROJECT_DIR="./"
CONFIG_FILE="red_vs_blue_config.yaml"
LOG_DIR="./pretest_logs"
mkdir -p "$LOG_DIR"

FILES=("orchestrator_stub.py" "whitelist_validator.py" "ssh_exec.py" "ai_agent_codellama.py" "whitelist.yaml" "$CONFIG_FILE")

echo "==============================="
echo "[TESTER] Starting Environment Test"
echo "==============================="

# ----------------------
# Load IPs, Users, Passwords
# ----------------------
CONFIG_DATA=$(python3 - << EOF
import yaml, sys, json
try:
    with open("red_vs_blue_config.yaml") as f:
        cfg = yaml.safe_load(f)
    hosts = {h['name']: h for h in cfg['hosts']}

    def get_field(name, key, default="MISSING"):
        if name not in hosts:
            return default
        return hosts[name].get(key, default)

    data = {
        "controller_red_ip": get_field("controller_red", "ip"),
        "controller_blue_ip": get_field("controller_blue", "ip"),
        "red_ip": get_field("red", "ip"),
        "blue_ip": get_field("blue", "ip"),
        "blue_net_ip": get_field("target_redblue", "ip_blue"),
        "red_net_ip": get_field("target_redblue", "ip_red"),
        "red_user": get_field("red", "user"),
        "red_pass": get_field("red", "password"),
        "blue_user": get_field("blue", "user"),
        "blue_pass": get_field("blue", "password"),
    }
    print(json.dumps(data))
except Exception as e:
    print(f"YAML load error: {e}", file=sys.stderr)
    sys.exit(1)
EOF
)

RED_VM_IP=$(echo "$CONFIG_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin)['red_ip'])")
BLUE_VM_IP=$(echo "$CONFIG_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin)['blue_ip'])")
CONTROLLER_RED_IP=$(echo "$CONFIG_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin)['controller_red_ip'])")
CONTROLLER_BLUE_IP=$(echo "$CONFIG_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin)['controller_blue_ip'])")
RED_NET_IP=$(echo "$CONFIG_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin)['red_net_ip'])")
BLUE_NET_IP=$(echo "$CONFIG_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin)['blue_net_ip'])")
RED_USER=$(echo "$CONFIG_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin)['red_user'])")
RED_PASS=$(echo "$CONFIG_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin)['red_pass'])")
BLUE_USER=$(echo "$CONFIG_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin)['blue_user'])")
BLUE_PASS=$(echo "$CONFIG_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin)['blue_pass'])")

echo ""
echo "==== Loaded Configuration ===="
echo " Controller (Red):  $CONTROLLER_RED_IP"
echo " Controller (Blue): $CONTROLLER_BLUE_IP"
echo " Red VM:            $RED_VM_IP  | User: $RED_USER  | Pass: $RED_PASS"
echo " Blue VM:           $BLUE_VM_IP | User: $BLUE_USER  | Pass: $BLUE_PASS"
echo " Target (Blue Net): $BLUE_NET_IP"
echo " Target (Red Net):  $RED_NET_IP"
echo "==============================="

# ----------------------
# Validate Required Files
# ----------------------
echo ""
echo "==== Checking Required Files ===="
missing=false
for f in "${FILES[@]}"; do
    if [ ! -f "$PROJECT_DIR$f" ]; then
        echo "Missing file: $f"
        missing=true
    else
        echo "Found: $f"
    fi
done
if [ "$missing" = true ]; then
    echo "One or more required files are missing. Please add them before continuing."
    exit 1
fi

# ----------------------
# AI Whitelist Validation Tests
# ----------------------
echo ""
echo "==== Running AI Whitelist Validation Tests ===="

PROMPTS=(
"Prompt 1: You are a cyber-range agent. Return ONLY valid JSON with keys: tool and params.
Use the tool 'nmap' and provide exactly one flag from the allowed enum: -sV, -sS, -A.
Do not include any explanation or text outside the JSON.
Example:
{
  \"tool\": \"nmap\",
  \"params\": {
      \"target\": \"${RED_VM_IP}\",
      \"flags\": \"-sV\"
  }
}
Propose a single action for target ${RED_VM_IP}."

"Prompt 2: You are a cyber-range agent. Return ONLY valid JSON with keys: tool and params.
Use the tool 'ping'.
Do not include any explanation, commentary, or text outside the JSON.
Example:
{
  \"tool\": \"ping\",
  \"params\": {
      \"target\": \"${RED_VM_IP}\"
  }
}
Propose a single action for target ${RED_VM_IP}."
)

for i in "${!PROMPTS[@]}"; do
    TIMESTAMP=$(date +"%Y%m%dT%H%M%S")
    RUN_DIR="$LOG_DIR/run_${TIMESTAMP}_$i"
    mkdir -p "$RUN_DIR"
    export RUN_DIR

    echo ""
    echo "---- Prompt $((i+1)) ----"
    echo "${PROMPTS[$i]}"

    if ! python3 - << EOF
import os, json, yaml
from ai_agent_codellama import get_action_from_llm
from whitelist_validator import validate_and_build

RUN_DIR = os.environ["RUN_DIR"]
with open("whitelist.yaml") as f:
    WL = yaml.safe_load(f)

prompt = """${PROMPTS[$i]}"""
try:
    action = get_action_from_llm(prompt)
except Exception as e:
    print(f"ERROR getting AI action: {e}")
    exit(1)

with open(os.path.join(RUN_DIR, "action.json"), "w") as f:
    json.dump(action, f, indent=2)

try:
    cmd, meta = validate_and_build(action)
    with open(os.path.join(RUN_DIR, "validated_command.txt"), "w") as f:
        f.write(cmd + "\n")
    print(f"[VALID] Command: {cmd}")
    with open(os.path.join(RUN_DIR, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
except Exception as e:
    print(f"[INVALID] {e}")
EOF
    then
        echo "[WARN] Prompt $((i+1)) test failed, continuing..."
    fi
done

# ----------------------
# SSH Connectivity Tests
# ----------------------
echo ""
echo "==== Testing SSH Connectivity (Controller → Red / Blue) ===="

if ! python3 - << EOF
import yaml
from ssh_exec import ssh_command

with open("red_vs_blue_config.yaml") as f:
    cfg = yaml.safe_load(f)
hosts = {h['name']: h for h in cfg['hosts']}

try:
    out_red = ssh_command(user=hosts['red']['user'], host=hosts['red']['ip'], password=hosts['red']['password'], command="hostname")
    print(f"[OK] SSH to Red VM ({hosts['red']['ip']}) successful: {out_red.strip()}")
except Exception as e:
    print(f"[FAIL] SSH to Red VM failed: {e}")

try:
    out_blue = ssh_command(user=hosts['blue']['user'], host=hosts['blue']['ip'], password=hosts['blue']['password'], command="hostname")
    print(f"[OK] SSH to Blue VM ({hosts['blue']['ip']}) successful: {out_blue.strip()}")
except Exception as e:
    print(f"[FAIL] SSH to Blue VM failed: {e}")
EOF
then
    echo "[WARN] SSH connectivity test encountered errors, continuing..."
fi

# ----------------------
# AI Ping Test (Red → Blue)
# ----------------------
echo ""
echo "==== AI Ping Test (Red → Blue) ===="

PROMPT_PING="You are a cyber-range agent. Return ONLY valid JSON with keys: tool, params.
Example ping:
{
  \"tool\": \"ping\",
  \"params\": {
      \"target\": \"${BLUE_NET_IP}\"
  }
}
Propose a single action to ping Blue VM (${BLUE_NET_IP}) from Red VM (${RED_NET_IP})."

if ! python3 - << EOF
import json
from ai_agent_codellama import get_action_from_llm
from whitelist_validator import validate_and_build

try:
    action = get_action_from_llm("""$PROMPT_PING""")
    cmd, meta = validate_and_build(action)
    print(f"[VALID] Ping command generated: {cmd}")
except Exception as e:
    print(f"[FAIL] Ping test failed: {e}")
EOF
then
    echo "[WARN] AI Ping test failed, continuing..."
fi

echo ""
echo "==== Pre-Test Completed ===="
echo "All results stored in: $LOG_DIR"
