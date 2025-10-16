import os
import argparse
import time

#
#   Example of commands run in command line for script to gather logs
#   Should run automatically however just in case.
#   python aggregate_runs.py --run 1 --auto-log auto_aggregator.log
#

parser = argparse.ArgumentParser(description="Aggregate Red, Blue VM logs, and optional auto log into a single Run log.")
parser.add_argument("--run", required=True, type=int, help="Run number to aggregate")
parser.add_argument("--log-dir", default="logs", help="Directory where VM logs are stored")
parser.add_argument("--output-dir", default="aggregated_logs", help="Directory to save combined logs")
parser.add_argument("--auto-log", default=None, help="Optional auto log file to include")
args = parser.parse_args()

RUN_NUMBER = args.run
LOG_DIR = args.log_dir
OUTPUT_DIR = args.output_dir
AUTO_LOG_FILE = os.path.join(LOG_DIR, args.auto_log) if args.auto_log else None

os.makedirs(OUTPUT_DIR, exist_ok=True)

red_log_file = os.path.join(LOG_DIR, f"Red_Run{RUN_NUMBER}.log")
blue_log_file = os.path.join(LOG_DIR, f"Blue_Run{RUN_NUMBER}.log")
combined_file = os.path.join(OUTPUT_DIR, f"Run{RUN_NUMBER}_Combined.log")

# Waiting for Red and Blue logs
print(f"Waiting for Red and Blue logs for Run {RUN_NUMBER}...")
while not (os.path.exists(red_log_file) and os.path.exists(blue_log_file)):
    time.sleep(2)

# Combines all logs
with open(combined_file, "w") as outfile:
    for log_file in [red_log_file, blue_log_file, AUTO_LOG_FILE]:
        if log_file and os.path.exists(log_file):
            outfile.write(f"\n--- {os.path.basename(log_file)} ---\n")
            with open(log_file, "r") as f:
                outfile.write(f.read())
        elif log_file:
            outfile.write(f"\n--- {os.path.basename(log_file)} NOT FOUND ---\n")

print(f"Aggregated log created: {combined_file}")
