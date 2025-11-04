import os
import time
import argparse

def aggregate_logs_for_run(run_number, log_dir="logs", output_dir="aggregated_logs", auto_log=None):
    """
    Aggregates Red/Blue VM logs and optional auto log into a single combined log for a given run.
    """
    os.makedirs(output_dir, exist_ok=True)

    red_log_file = os.path.join(log_dir, f"Red_Run{run_number}.log")
    blue_log_file = os.path.join(log_dir, f"Blue_Run{run_number}.log")
    combined_file = os.path.join(output_dir, f"Run{run_number}_Combined.log")
    auto_log_file = os.path.join(log_dir, auto_log) if auto_log else None

    # Wait for logs to exist
    print(f"Waiting for Red and Blue logs for Run {run_number}...")
    while not (os.path.exists(red_log_file) and os.path.exists(blue_log_file)):
        time.sleep(2)

    # Combine logs
    with open(combined_file, "w") as outfile:
        for log_file in [red_log_file, blue_log_file, auto_log_file]:
            if log_file and os.path.exists(log_file):
                outfile.write(f"\n--- {os.path.basename(log_file)} ---\n")
                with open(log_file, "r") as f:
                    outfile.write(f.read())
            elif log_file:
                outfile.write(f"\n--- {os.path.basename(log_file)} NOT FOUND ---\n")

    print(f"Aggregated log created: {combined_file}")
    return combined_file  # return path for orchestrator or web UI

# ------------------------------------------------------------
# CLI entry point (preserve backward compatibility)
# ------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggregate Red, Blue VM logs, and optional auto log into a single Run log.")
    parser.add_argument("--run", required=True, type=int, help="Run number to aggregate")
    parser.add_argument("--log-dir", default="logs", help="Directory where VM logs are stored")
    parser.add_argument("--output-dir", default="aggregated_logs", help="Directory to save combined logs")
    parser.add_argument("--auto-log", default=None, help="Optional auto log file to include")
    args = parser.parse_args()

    aggregate_logs_for_run(
        run_number=args.run,
        log_dir=args.log_dir,
        output_dir=args.output_dir,
        auto_log=args.auto_log
    )
