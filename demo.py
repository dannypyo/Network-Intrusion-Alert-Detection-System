"""One command to run the whole system for a demo.

    python demo.py

Starts the server, the target service and five agents with demo settings, waits until
everything is ready, and prints the dashboard address. Press Ctrl+C to stop everything.
Each process writes its output to demo_logs/. Uses only the Python standard library.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ---------- Settings ----------

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "demo_logs"
DB_FILE = ROOT / "server" / "data" / "monitor.db"
AUTH_LOG = ROOT / "env" / "logs" / "auth.log"
SERVER_URL = "http://127.0.0.1:8000"
PORTS = {8000: "the server", 9000: "the target service", 9001: "the target's control port"}

# Shorter timers than the defaults so the demo moves quickly; alerts stay up for 3 minutes
SERVER_SETTINGS = {"OFFLINE_THRESHOLD_S": "15", "SWEEP_INTERVAL_S": "2", "ALERT_EXPIRY_S": "180"}
REPORT_INTERVAL_S = "5"

# agent id: (services it monitors, interfaces counted for traffic, reads the login log)
AGENTS = {
    "agent-web-01": ("target=http://127.0.0.1:9000/", "loopback", True),
    "agent-web-02": ("target=http://127.0.0.1:9000/", "external", False),
    "agent-ctl-01": ("control=tcp://127.0.0.1:9001", "external", False),
    "agent-ctl-02": ("control=tcp://127.0.0.1:9001", "external", False),
    "agent-srv-01": ("server=http://127.0.0.1:8000/health", "external", False),
}

READY_TIMEOUT_S = 20

# Ignore proxy settings: every request goes to this machine
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class DemoError(Exception):
    """A problem that stops the demo. The message is shown to the user."""


# ---------- Process control ----------

def log_tail(name, lines=20):
    """The last lines of a process's log, for error messages."""
    try:
        text = (LOG_DIR / f"{name}.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(no log)"
    return f"Last lines of demo_logs/{name}.log:\n" + "\n".join(text.splitlines()[-lines:])


class Processes:
    """Starts the demo's processes, watches them, and stops them in reverse order."""

    def __init__(self):
        self.running = []  # (name, process, log file)

    def start(self, name, args, cwd=ROOT, env=None):
        log = open(LOG_DIR / f"{name}.log", "w", encoding="utf-8")
        full_env = {**os.environ, "PYTHONUNBUFFERED": "1", **(env or {})}
        # Detach from the terminal's Ctrl+C, so this script can stop everything in order
        if os.name == "nt":
            detach = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            detach = {"start_new_session": True}
        process = subprocess.Popen([sys.executable, *args], cwd=cwd, env=full_env,
                                   stdout=log, stderr=subprocess.STDOUT, **detach)
        self.running.append((name, process, log))

    def check_alive(self):
        """Stop the demo if any process has exited."""
        for name, process, _ in self.running:
            if process.poll() is not None:
                raise DemoError(f"{name} stopped unexpectedly (exit code {process.returncode}).\n{log_tail(name)}")

    def stop_all(self):
        """Stop the agents first and the server last, giving each 5 s to exit cleanly."""
        for _, process, log in reversed(self.running):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            log.close()
        self.running.clear()


# ---------- Readiness checks ----------

def port_in_use(port):
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def get_json(path):
    with OPENER.open(SERVER_URL + path, timeout=2) as response:
        return json.loads(response.read())


def server_ready():
    return get_json("/health") == {"ok": True}


def target_ready():
    return port_in_use(9000) and port_in_use(9001)


def agents_online():
    statuses = {agent["agent_id"]: agent["status"] for agent in get_json("/agents")}
    return all(statuses.get(agent_id) == "online" for agent_id in AGENTS)


def wait_until(description, check, processes, log_name):
    """Print progress dots until check() is true, or stop with the log's last lines."""
    print(f"{description}..", end="", flush=True)
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        processes.check_alive()
        try:
            if check():
                print(" ready")
                return
        except (OSError, ValueError):
            pass  # not answering yet
        time.sleep(0.5)
        print(".", end="", flush=True)
    print()
    raise DemoError(f"{description} was not ready after {READY_TIMEOUT_S} s.\n{log_tail(log_name)}")


# ---------- Main ----------

def clear_old_data():
    """Start each demo with an empty database and login log."""
    for path in (DB_FILE, DB_FILE.with_name("monitor.db-wal"), DB_FILE.with_name("monitor.db-shm"), AUTH_LOG):
        path.unlink(missing_ok=True)


def start_everything(processes):
    processes.start("server", ["-m", "app"], cwd=ROOT / "server", env={
        **SERVER_SETTINGS,
        "HOST": "127.0.0.1",
        "PORT": "8000",
        "DB_PATH": str(DB_FILE),
        "EXPECTED_AGENTS": ",".join(AGENTS),  # shown as pending until each one reports
    })
    wait_until("Starting server", server_ready, processes, "server")

    processes.start("target", [str(ROOT / "env" / "target_service.py")])
    wait_until("Starting target service", target_ready, processes, "target")

    for agent_id, (services, interface, reads_login_log) in AGENTS.items():
        processes.start(agent_id, [str(ROOT / "monitoring_agent" / "main.py")],
                        cwd=ROOT / "monitoring_agent", env={
            "AGENT_ID": agent_id,
            "SERVER_URL": SERVER_URL,
            "REPORT_INTERVAL_S": REPORT_INTERVAL_S,
            "SERVICES": services,
            "TRAFFIC_INTERFACE": interface,
            # os.devnull is always empty, so the other agents never report failed logins
            "AUTH_LOG_PATH": str(AUTH_LOG) if reads_login_log else os.devnull,
        })
    wait_until(f"Starting {len(AGENTS)} agents", agents_online, processes, "agent-web-01")


def main():
    busy = [f"{port} ({owner})" for port, owner in PORTS.items() if port_in_use(port)]
    if busy:
        raise DemoError(f"Port {', '.join(busy)} is already in use. "
                        "Stop whatever is using it (for example a server started earlier) and try again.")
    print("Ports 8000, 9000 and 9001 are free")

    LOG_DIR.mkdir(exist_ok=True)
    clear_old_data()
    print("Cleared the database and login log")

    processes = Processes()
    try:
        start_everything(processes)
        print(f"\nDashboard: {SERVER_URL}/")
        print("Press Ctrl+C to stop.")
        while True:
            processes.check_alive()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        processes.stop_all()
        print("Stopped.")


if __name__ == "__main__":
    try:
        main()
    except DemoError as error:
        print(f"\nError: {error}", file=sys.stderr)
        sys.exit(1)
