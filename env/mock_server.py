import argparse
import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Load Matthew's detection engine from server/app/detection.py.
SERVER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server")
sys.path.insert(0, os.path.abspath(SERVER_DIR))
from app.detection import DetectionEngine  # noqa: E402

engine = DetectionEngine()
engine_lock = threading.Lock()

last_seen = {}       # agent_id -> time of last report
offline = set()      # agents already reported as offline


def summarize(report):
    """One short line describing a report."""
    t = report.get("traffic", {})
    interval = t.get("interval_s") or 1
    rate = (t.get("bytes_in", 0) + t.get("bytes_out", 0)) / interval
    parts = [f"traffic {rate / 1_000_000:.2f} MB/s"]
    for s in report.get("services", []):
        status = "up" if s.get("up") else "DOWN"
        parts.append(f"{s.get('name')} {status} {s.get('response_ms')} ms")
    parts.append(f"failed_logins {len(report.get('failed_logins', []))}")
    return ", ".join(parts)


class ReportHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/report":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            report = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        agent = report.get("agent_id", "?")
        now = time.strftime("%H:%M:%S")
        last_seen[agent] = time.monotonic()
        if agent in offline:
            offline.discard(agent)
            print(f"{now}  [BACK ONLINE] {agent}", flush=True)

        print(f"{now}  report from {agent}: {summarize(report)}", flush=True)

        # Run the detection rules. If they crash, show why instead of dying.
        try:
            with engine_lock:
                alerts = engine.evaluate_report(report)
        except Exception as error:
            print(f"{now}  !! detection.py crashed on this report: "
                  f"{type(error).__name__}: {error}", flush=True)
            traceback.print_exc(limit=1)
            alerts = []

        for a in alerts:
            print(f"{now}  ** ALERT {a['type']} ({a['severity']}) {a['agent_id']}: {a['message']}", flush=True)

        body = b'{"status": "received"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def watch_for_offline(threshold_s):
    """Every few seconds, flag agents that have gone quiet."""
    while True:
        time.sleep(5)
        for agent, seen in list(last_seen.items()):
            if agent not in offline and time.monotonic() - seen > threshold_s:
                offline.add(agent)
                print(f"{time.strftime('%H:%M:%S')}  ** ALERT AGENT_OFFLINE: "
                      f"{agent} has not reported for over {threshold_s}s", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Mock central server for testing")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--offline-threshold", type=int, default=30)
    args = parser.parse_args()

    threading.Thread(target=watch_for_offline, args=(args.offline_threshold,), daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ReportHandler)
    print(f"Mock server listening on http://127.0.0.1:{args.port}/report", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping mock server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()