"""
orchestrator.py
Main orchestrator logic and Integrates AI decision-making while checking against whitelist.
"""

from ai_agent_codellama import get_action_from_llm
from whitelist_validator import build_command
import yaml
import os
import json
import time

#   INITIALIZATION
print("------------------------------------------------------------")
print("AI Simulation Orchestrator - Starting Up")
print("------------------------------------------------------------")

# Ensure working directory is script folder
base_dir = os.path.dirname(os.path.abspath(__file__))

# Load whitelist
print("\n[INFO] Loading whitelist policy (whitelist.yaml)...")
try:
    with open(os.path.join(base_dir, "whitelist.yaml"), "r") as f:
        WL = yaml.safe_load(f)
    print("[OK] Whitelist successfully loaded.")
except Exception as e:
    print(f"[ERROR] Failed to load whitelist: {e}")
    exit(1)

#   PROMPT
prompt = (
    "You are an automated agent. Reply with only a single valid JSON object "
    "and nothing else (no code fences, no extra text). "
    "The JSON must use only double quotes and match this schema:\n"
    '{"tool": "<tool name>", "params": {...}}\n'
    "Allowed tool values: nmap, ping, tcpdump, iptables, hydra.\n"
    "The 'target' parameter must always be a single IPv4 address (e.g., 192.168.60.3), not a range or CIDR.\n"
    "Example valid response:\n"
    '{"tool": "ping", "params": {"target": "192.168.60.3"}}'

)

#   Get AI Action
print("\n[STEP 1] Querying AI agent for next action...")
time.sleep(1)

raw_action = get_action_from_llm(prompt)
print("\n[DEBUG] Raw AI Output Received:")
print("------------------------------------------------------------")
print(raw_action)
print("------------------------------------------------------------")

#   Validate AI output type
print("\n[STEP 2] Validating AI output format...")
if isinstance(raw_action, dict):
    action = raw_action
    print("[OK] AI output is a valid Python dictionary.")
else:
    try:
        action = json.loads(raw_action)
        print("[OK] JSON successfully parsed.")
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON returned\nDetails: {e}")
        exit(1)

#   Whitelist Validation
print("\n[STEP 3] Validating AI action against whitelist...")
try:
    cmd = build_command(action)
    print("[OK] Action approved by whitelist.")
except Exception as e:
    print(f"[ERROR] Denied Action: {e}")
    exit(1)

#   Final Output
print("\n[STEP 4] Command successfully built and ready for execution.")
print("------------------------------------------------------------")
print(f"Final Command: {cmd}")
print("------------------------------------------------------------")

print("\n[COMPLETE] Simulation step completed successfully.\n")
