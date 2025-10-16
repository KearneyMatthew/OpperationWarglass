import os
import subprocess
from datetime import datetime
import argparse

#
#   Example of commands run in command line for script to gather logs
#   python command_logger_auto_aggregate.py --vm Red --run 1
#   python command_logger_auto_aggregate.py --vm Blue --run 1
#
parser = argparse.ArgumentParser(description="Simple command logger for Red/Blue VM simulation with automatic aggregation.")
parser.add_argument("--vm", required=True, choices=["Red", "Blue"], help="VM name")
parser.add_argument("--run", required=True, type=int, help="Run number")
parser.add_argument("--log-dir", default="logs", help="Directory to save VM logs")
parser.add_argument("--output-dir", default="aggregated_logs", help="Directory to save combined logs")
parser.add_argument("--auto-log", default=None, help="Optional auto log file to include")
args = parser.parse_args()

VM_NAME = args.vm
RUN_NUMBER = args.run
LOG_DIR = args.log_dir
OUTPUT_DIR = args.output_dir
AUTO_LOG_FILE = args.auto_log

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

#
# Per-VM log file
#
log_file = os.path.join(LOG_DIR, f"{VM_NAME}_Run{RUN_NUMBER}.log")

def log_command(command: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a") as f:
        f.write(f"[{timestamp}] {command}\n")

#
# Main loop
#
if __name__ == "__main__":
    while True:
        cmd = input(f"{VM_NAME}> Enter command (or 'exit' to stop): ")
        if cmd.lower() == "exit":
            break
        log_command(cmd)
        subprocess.run(cmd, shell=True)

    #
    # Automatic aggregation/combination
    #
    print(f"Running aggregator for Run {RUN_NUMBER}...")
    aggregator_args = [
        "python", "aggregate_runs.py",
        "--run", str(RUN_NUMBER),
        "--log-dir", LOG_DIR,
        "--output-dir", OUTPUT_DIR
    ]
    if AUTO_LOG_FILE:
        aggregator_args += ["--auto-log", AUTO_LOG_FILE]

    subprocess.run(aggregator_args)
