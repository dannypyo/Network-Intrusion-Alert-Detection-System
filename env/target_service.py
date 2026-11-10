import argparse
import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# Where failed logins are written, one JSON object per line.
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
AUTH_LOG = os.path.join(LOG_DIR, "auth.log")

# The only username/password that logs in successfully.
VALID_USER = "admin"
VALID_PASSWORD = "password123"

# Shared settings that the control port changes.
state = {
    "latency_ms": 0,   # extra wait added to GET /
    "up": True,        # is the service port accepting connections?
}
state_lock = threading.Lock()
log_lock = threading.Lock()


def send_json(handler, status, data):
    """Send a small JSON reply."""
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def log_failed_login(source_ip, username):
    """Append one failed login to logs/auth.log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_ip": source_ip,
        "username": username,
    }
    with log_lock:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(AUTH_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


class ServiceHandler(BaseHTTPRequestHandler):
    """Handles requests on the service port (the one the agent watches)."""

    def do_GET(self):
        url = urlparse(self.path)

        if url.path == "/":
            with state_lock:
                delay = state["latency_ms"]
            if delay:
                time.sleep(delay / 1000)
            send_json(self, 200, {"service": "target", "ok": True})

        elif url.path == "/big":
            # Send N megabytes of zeros, in 64 KB pieces.
            mb = int(parse_qs(url.query).get("mb", ["5"])[0])
            total = mb * 1024 * 1024
            chunk = b"\0" * 65536
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(total))
            self.end_headers()
            sent = 0
            while sent < total:
                piece = chunk[: min(len(chunk), total - sent)]
                self.wfile.write(piece)
                sent += len(piece)

        else:
            send_json(self, 404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/login":
            send_json(self, 404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            send_json(self, 400, {"error": "invalid JSON"})
            return

        # The trigger script can pretend to be another computer by sending
        # an X-Source-IP header. Otherwise we use the real address.
        source_ip = self.headers.get("X-Source-IP") or self.client_address[0]
        username = data.get("username", "")

        if username == VALID_USER and data.get("password") == VALID_PASSWORD:
            send_json(self, 200, {"login": "ok"})
        else:
            log_failed_login(source_ip, username)
            send_json(self, 401, {"login": "failed"})

    def log_message(self, fmt, *args):
        # Keep the terminal quiet; the agent requests / every few seconds.
        pass


class ServicePort:
    """Starts and stops the service port so we can simulate an outage."""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server = None
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.server:
                return
            self.server = ThreadingHTTPServer((self.host, self.port), ServiceHandler)
            self.server.daemon_threads = True
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
        with state_lock:
            state["up"] = True
        print(f"[service] UP on http://{self.host}:{self.port}", flush=True)

    def stop(self):
        with self.lock:
            if not self.server:
                return
            self.server.shutdown()      # stop answering requests
            self.server.server_close()  # close the socket -> connection refused
            self.server = None
        with state_lock:
            state["up"] = False
        print("[service] DOWN (connections will be refused)", flush=True)


def make_control_handler(service):
    class ControlHandler(BaseHTTPRequestHandler):
        """Handles requests on the control port (used by trigger scripts)."""

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)

            if url.path == "/slow":
                ms = int(query.get("ms", ["1500"])[0])
                with state_lock:
                    state["latency_ms"] = ms
                print(f"[control] slow mode: GET / now waits {ms} ms", flush=True)
            elif url.path == "/fast":
                with state_lock:
                    state["latency_ms"] = 0
                print("[control] normal speed", flush=True)
            elif url.path == "/down":
                service.stop()
            elif url.path == "/up":
                service.start()
            elif url.path != "/status":
                send_json(self, 404, {"error": "not found"})
                return

            with state_lock:
                send_json(self, 200, dict(state))

        def log_message(self, fmt, *args):
            pass

    return ControlHandler


def main():
    parser = argparse.ArgumentParser(description="Target service for the test environment")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000, help="service port the agent checks")
    parser.add_argument("--control-port", type=int, default=9001, help="port the trigger scripts use")
    args = parser.parse_args()

    service = ServicePort(args.host, args.port)
    service.start()

    control = ThreadingHTTPServer((args.host, args.control_port), make_control_handler(service))
    print(f"[control] listening on http://{args.host}:{args.control_port}", flush=True)
    print(f"[logins] failed logins go to {AUTH_LOG}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    try:
        control.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping target service.")
    finally:
        control.server_close()
        service.stop()


if __name__ == "__main__":
    main()