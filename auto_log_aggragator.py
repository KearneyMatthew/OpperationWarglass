import os
import time
import argparse

#
# Example of command line argument: python auto_log_aggregator.py --run #
#
parser = argparse.ArgumentParser(description="Automatically aggregate Red/Blue logs once both exist.")
parser.add_argument("--run", required=True, type=int, help="Run number to aggregate")
parser.add_argument("--log-dir", default="logs", help="Directory where individual VM logs are stored")
parser.add_argument("--output-dir", default="aggregated_logs", help="Directory to save aggregated logs")
parser.add_argument("--check-interval", type=int, default=5, help="Seconds between checks for log files")
args = parser.parse_args()

RUN_NUMBER = args.run
LOG_DIR = args.log_dir
OUTPUT_DIR = args.output_dir
CHECK_INTERVAL = args.check_interval
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Expected files
def expected_files(run_number):
    return [
        os.path.join(LOG_DIR, f"Red_Run{run_number}_success.log"),
        os.path.join(LOG_DIR, f"Red_Run{run_number}_failure.log"),
        os.path.join(LOG_DIR, f"Blue_Run{run_number}_success.log"),
        os.path.join(LOG_DIR, f"Blue_Run{run_number}_failure.log"),
    ]

def find_logs(run_number):
    "Return list of Red and Blue logs if they exist."
    files = expected_files(run_number)
    red_log = next((f for f in files if os.path.exists(f) and "Red" in f), None)
    blue_log = next((f for f in files if os.path.exists(f) and "Blue" in f), None)
    return red_log, blue_log

def aggregate_logs(red_log, blue_log, run_number):
    output_file = os.path.join(OUTPUT_DIR, f"Run{run_number}_Combined.log")
    with open(output_file, "w") as outfile:
        for file_path in [red_log, blue_log]:
            if file_path:
                with open(file_path, "r") as f:
                    outfile.write(f"\n--- {os.path.basename(file_path)} ---\n")
                    outfile.write(f.read())
            else:
                outfile.write(f"\n--- {file_path} NOT FOUND ---\n")
    print(f"Aggregated logs saved to {output_file}")

#
# Watch loop
#
print(f"Waiting for Red and Blue logs for run {RUN_NUMBER}...")
while True:
    red_log, blue_log = find_logs(RUN_NUMBER)
    if red_log and blue_log:
        aggregate_logs(red_log, blue_log, RUN_NUMBER)
        break
    time.sleep(CHECK_INTERVAL)
