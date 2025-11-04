# app.py
import os
import time
import uuid
import threading
import queue
import subprocess
import json
from flask import Flask, request, jsonify, Response, send_from_directory, abort

# Configuration
RUNS_DIR = "runs"
ORCHESTRATOR = "orchestrator_stub.py"
HOST = "0.0.0.0"
PORT = 8000

# Create Flask app
app = Flask(__name__)
os.makedirs(RUNS_DIR, exist_ok=True)

runs = {}
runs_lock = threading.Lock()

print("Flask root path:", app.root_path)
print("Current working dir:", os.getcwd())
print("Index exists:", os.path.exists('index.html'))

@app.route("/")
def index():
    return send_from_directory('.', 'index.html')

def reader_thread(proc, q, logfile_path, run_id):
    """
    Read subprocess stdout/stderr, push structured JSON to queue, and write log file.
    Handles both JSON output and plain text fallback.
    """
    try:
        with open(logfile_path, "a", encoding="utf-8") as f:
            for raw_line in iter(proc.stdout.readline, ''):
                if not raw_line:
                    break
                text = raw_line.rstrip() if isinstance(raw_line, str) else raw_line.decode(errors="replace").rstrip()
                f.write(text + "\n")
                f.flush()
                try:
                    obj = json.loads(text)
                    q.put(obj)
                except json.JSONDecodeError:
                    q.put({"type": "log", "message": text})
    except Exception as e:
        q.put({"type": "error", "message": f"Reader error: {e}"})

    proc.wait()
    q.put({"type": "complete", "message": "Run finished"})

    with runs_lock:
        runs.pop(run_id, None)


@app.route("/simulate", methods=["POST"])
def simulate():
    """
    Start a single orchestrator run with readable run ID.
    Rejects if another run is active.
    """
    data = request.get_json(force=True)
    attack = data.get("attack")
    purpose = data.get("purpose")
    defense = data.get("defense")

    if not all([attack, purpose, defense]):
        return jsonify({"error": "attack, purpose, and defense are required"}), 400

    with runs_lock:
        for rid, meta in runs.items():
            if meta.get("proc") and meta["proc"].poll() is None:
                return jsonify({
                    "error": "Another run is already in progress",
                    "active_run_id": rid
                }), 409

    def short_token(s, limit=16):
        t = str(s).strip().lower().replace(" ", "_")
        t = "".join(ch for ch in t if (ch.isalnum() or ch in "_-"))
        return t[:limit]

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    run_id = f"{timestamp}_{short_token(attack,12)}-{short_token(purpose,20)}-{short_token(defense,12)}-{uuid.uuid4().hex[:6]}"
    logfile = os.path.join(RUNS_DIR, f"run-{run_id}.log")

    cmd = [
        "python3", ORCHESTRATOR,
        "--attack", attack,
        "--purpose", purpose,
        "--defense", defense,
        "--run-id", run_id
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True
        )
    except Exception as e:
        return jsonify({"error": f"Failed to start orchestrator: {e}"}), 500

    q = queue.Queue()
    with runs_lock:
        runs[run_id] = {"queue": q, "proc": proc, "logfile": logfile}

    t = threading.Thread(target=reader_thread, args=(proc, q, logfile, run_id), daemon=True)
    t.start()

    return jsonify({
        "run_id": run_id,
        "logfile": logfile,
        "attack": attack,
        "purpose": purpose,
        "defense": defense,
        "start_time": timestamp
    })


@app.route("/stream/<run_id>")
def stream(run_id):
    with runs_lock:
        meta = runs.get(run_id)
    if not meta:
        return abort(404, description="Run ID not found")
    q = meta["queue"]

    def event_stream():
        while True:
            try:
                obj = q.get(timeout=0.5)
            except queue.Empty:
                if meta["proc"].poll() is not None and q.empty():
                    break
                continue
            yield f"data: {json.dumps(obj)}\n\n"
            if obj.get("type") == "complete":
                break

    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/logs", methods=["GET"])
def list_logs():
    files = [{"name": fn, "mtime": os.path.getmtime(os.path.join(RUNS_DIR, fn))}
             for fn in os.listdir(RUNS_DIR) if os.path.isfile(os.path.join(RUNS_DIR, fn))]
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return jsonify(files)


@app.route("/log")
def get_log():
    filename = request.args.get("file")
    if not filename:
        return abort(400, description="file parameter is required")
    path = os.path.join(RUNS_DIR, filename)
    if not os.path.exists(path) or not os.path.isfile(path):
        return abort(404, description="file not found")
    return send_from_directory(RUNS_DIR, filename, mimetype="text/plain")


if __name__ == "__main__":
    print(f"Starting Flask on http://{HOST}:{PORT} ...")
    app.run(host=HOST, port=PORT, threaded=True)
