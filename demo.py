"""One command to run the whole system for a demo.

    python demo.py                            # the full sequence
    python demo.py --talk 30                  # 30 s pause after each detection (default 45)
    python demo.py --only brute-force,outage  # just these attacks, in their usual order
    python demo.py --loop                     # repeat the sequence until Ctrl+C

Starts the server, the target service and five agents with demo settings, then runs a
sequence of attacks and records when each one is detected. Progress appears on the
dashboard (from GET /timeline) and in this terminal. Press Ctrl+C to stop everything.
Each process writes its output to demo_logs/. Uses only the Python standard library.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ---------- Settings ----------

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "demo_logs"
DB_FILE = ROOT / "server" / "data" / "monitor.db"
AUTH_LOG = ROOT / "env" / "logs" / "auth.log"
TIMELINE_FILE = LOG_DIR / "timeline.json"
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
DETECT_TIMEOUT_S = 60    # an attack not detected within this is marked missed
RECOVER_TIMEOUT_S = 30   # time allowed for the stopped agent to come back online
TALK_TIME_S = 45         # default pause after each detection before the next attack (--talk)

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


def launch(name, args, cwd=ROOT, env=None, log_mode="w"):
    """Start a Python process with its output going to demo_logs/<name>.log."""
    log = open(LOG_DIR / f"{name}.log", log_mode, encoding="utf-8")
    full_env = {**os.environ, "PYTHONUNBUFFERED": "1", **(env or {})}
    # Detach from the terminal's Ctrl+C, so this script can stop everything in order
    if os.name == "nt":
        detach = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        detach = {"start_new_session": True}
    process = subprocess.Popen([sys.executable, *args], cwd=cwd, env=full_env,
                               stdout=log, stderr=subprocess.STDOUT, **detach)
    return process, log


def stop(process, log):
    """Ask a process to exit, force it after 5 s, and close its log."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    log.close()


class Processes:
    """Starts the demo's processes, watches them, and stops them in reverse order."""

    def __init__(self):
        self.running = []   # (name, process, log file), in start order
        self.how = {}       # name -> (args, cwd, env), so a stopped process can be restarted
        self.attacks = []   # (process, log file) of attack scripts still running

    def start(self, name, args, cwd=ROOT, env=None, log_mode="w"):
        self.how[name] = (args, cwd, env)
        process, log = launch(name, args, cwd, env, log_mode)
        self.running.append((name, process, log))

    def stop(self, name):
        """A planned stop: the process is no longer watched for crashes."""
        for entry in self.running:
            if entry[0] == name:
                self.running.remove(entry)
                stop(entry[1], entry[2])
                return

    def restart(self, name):
        args, cwd, env = self.how[name]
        self.start(name, args, cwd, env, log_mode="a")  # keep the log from before the stop

    def run_attack(self, script, *args):
        """Start one of the env/ trigger scripts; returns its process."""
        process, log = launch(script, [str(ROOT / "env" / f"{script}.py"), *args])
        self.attacks.append((process, log))
        return process

    def check_alive(self):
        """Stop the demo if any watched process has exited."""
        for name, process, _ in self.running:
            if process.poll() is not None:
                raise DemoError(f"{name} stopped unexpectedly (exit code {process.returncode}).\n{log_tail(name)}")

    def stop_all(self):
        """Stop running attacks, then the agents, then the target, then the server."""
        for process, log in self.attacks:
            stop(process, log)
        self.attacks.clear()
        for _, process, log in reversed(self.running):
            stop(process, log)
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


def agent_statuses():
    return {agent["agent_id"]: agent["status"] for agent in get_json("/agents")}


def agents_online():
    statuses = agent_statuses()
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


# ---------- Attack sequence ----------

def utc_now():
    return datetime.now(timezone.utc)


def to_text(moment):
    """The server's timestamp format, e.g. 2026-11-11T20:00:05.000000Z."""
    return moment.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="microseconds") + "Z"


def say(text):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {text}", flush=True)


@dataclass
class Step:
    key: str             # short name used by --only
    name: str
    description: str
    expect: str | None   # alert type this step should raise; None for the recovery step
    action: object       # function(processes) that starts the step; may return a process
    state: str = "pending"
    started: datetime | None = None
    detected_in_s: float | None = None
    raised_by: list = field(default_factory=list)  # agents that raised the expected alert
    detail: str | None = None
    process: object = None

    def as_json(self):
        detail = self.detail
        if self.raised_by:
            detail = "Raised by " + ", ".join(self.raised_by)
        return {"name": self.name, "description": self.description, "expect": self.expect,
                "state": self.state, "started_at": to_text(self.started) if self.started else None,
                "detected_in_s": self.detected_in_s, "detail": detail}


def attack(script, *args):
    return lambda processes: processes.run_attack(script, *args)


def make_steps():
    """A fresh list of steps, in the order they run. Each loop round gets its own copy."""
    return [
        Step("brute-force", "Brute-force login", "8 wrong passwords from 10.0.0.66 against the target's login page",
             "BRUTE_FORCE_LOGIN", attack("trigger_failed_logins")),
        Step("traffic-spike", "Traffic spike", "30 s of parallel large downloads from the target service",
             "TRAFFIC_SPIKE", attack("trigger_traffic_spike")),
        Step("slow", "Slow responses", "The target adds 1,500 ms to every response for 30 s",
             "HIGH_LATENCY", attack("trigger_slow_response")),
        Step("outage", "Service outage", "The target refuses connections for 30 s, then recovers",
             "SERVICE_DOWN", attack("trigger_service_down")),
        Step("offline", "Agent goes offline", "agent-ctl-02 stops reporting",
             "AGENT_OFFLINE", lambda processes: processes.stop("agent-ctl-02")),
        Step("offline", "Agent back online", "agent-ctl-02 starts reporting again",
             None, lambda processes: processes.restart("agent-ctl-02")),
    ]


STEP_KEYS = list(dict.fromkeys(step.key for step in make_steps()))  # in order, without repeats


class Sequence:
    """Runs the steps in order, watches the alerts, and keeps the timeline file current."""

    def __init__(self, processes, steps, talk_time_s, last_seen_by_id=None):
        self.processes = processes
        self.steps = steps
        self.talk_time_s = talk_time_s
        self.current = -1           # index of the step that is running
        # alert id -> last_seen when last checked; shared between loop rounds
        self.last_seen_by_id = {} if last_seen_by_id is None else last_seen_by_id
        self.unexpected = []        # keys of alerts no step expected
        self.started = utc_now()
        self.finished = None

    def write_timeline(self):
        data = {
            "active": self.finished is None,
            "started_at": to_text(self.started),
            "finished_at": to_text(self.finished) if self.finished else None,
            "settings": {"report_interval_s": int(REPORT_INTERVAL_S),
                         **{name.lower(): int(value) for name, value in SERVER_SETTINGS.items()},
                         "talk_time_s": self.talk_time_s},
            "steps": [step.as_json() for step in self.steps],
            "unexpected_alerts": self.unexpected,
        }
        # Write a temporary file, then rename it: the server never sees a half-written file
        temporary = TIMELINE_FILE.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temporary, TIMELINE_FILE)

    def watch(self):
        """Check for crashes, then sort every new or re-signaled alert."""
        self.processes.check_alive()
        try:
            alerts = get_json("/alerts?status=all&limit=500")
        except (OSError, ValueError):
            return  # the server is busy; try again next second
        for alert in alerts:
            previous = self.last_seen_by_id.get(alert["id"])
            if previous is None:
                self.sort_alert(alert, signaled_at=alert["first_seen"], is_new=True)
            elif alert["last_seen"] != previous:
                # An active alert signaled again, e.g. the same attack in the next loop round
                self.sort_alert(alert, signaled_at=alert["last_seen"], is_new=False)
            self.last_seen_by_id[alert["id"]] = alert["last_seen"]
        self.write_timeline()

    def sort_alert(self, alert, signaled_at, is_new):
        """Credit the alert to this step or the previous one; otherwise a new alert is unexpected."""
        signaled = datetime.fromisoformat(signaled_at)
        # The previous step counts too: its effects can arrive just after the next step starts
        for index in (self.current, self.current - 1):
            if index < 0:
                continue
            step = self.steps[index]
            if step.expect == alert["type"] and step.started and signaled >= step.started:
                if step.detected_in_s is None:
                    step.detected_in_s = round((signaled - step.started).total_seconds(), 1)
                    step.state = "detected"
                    say(f"DETECTED  {alert['key']}  in {step.detected_in_s} s")
                if alert["agent_id"] and alert["agent_id"] not in step.raised_by:
                    step.raised_by.append(alert["agent_id"])
                return
        if is_new:
            # Repeats of an older alert are an ongoing condition, not a new false positive
            self.unexpected.append(alert["key"])
            say(f"UNEXPECTED alert {alert['key']}")

    def wait(self, seconds, until=None):
        """Watch alerts once a second for up to `seconds`, or until until() is true."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.watch()
            if until and until():
                return True
            time.sleep(1)
        return False

    def run(self):
        self.write_timeline()
        for index, step in enumerate(self.steps):
            self.current = index
            step.started = utc_now()
            step.state = "running"
            say(f"STEP {index + 1}/{len(self.steps)}  {step.name}: {step.description}")
            if step.expect:
                say(f"           Expecting {step.expect}")
            step.process = step.action(self.processes)
            self.write_timeline()

            if step.expect:
                detected = self.wait(DETECT_TIMEOUT_S, until=lambda: step.detected_in_s is not None)
            else:
                detected = self.wait(RECOVER_TIMEOUT_S, until=self.agent_recovered)
                if detected:
                    step.state = "done"
                    step.detail = f"Back online after {(utc_now() - step.started).total_seconds():.1f} s; offline alert resolved"
                    say(step.detail)

            if not detected:
                step.state = "missed"
                step.detail = "No alert within the time limit" if step.expect else "Did not come back online in time"
                say(f"MISSED    {step.name}")
                talk_until = time.monotonic()  # no talk time after a miss
            else:
                talk_until = time.monotonic() + self.talk_time_s
            self.write_timeline()

            # Before the next step: let the attack script finish, and leave time to talk
            if index < len(self.steps) - 1:
                self.wait(max(0.0, talk_until - time.monotonic()))
                while step.process and step.process.poll() is None:
                    self.wait(1)

        self.finished = utc_now()
        self.write_timeline()

    def agent_recovered(self):
        """agent-ctl-02 is online again and its offline alert is resolved."""
        try:
            online = agent_statuses().get("agent-ctl-02") == "online"
            active_keys = {alert["key"] for alert in get_json("/alerts")}
        except (OSError, ValueError):
            return False
        return online and "AGENT_OFFLINE:agent-ctl-02" not in active_keys


# ---------- Results ----------

def results_table(sequence):
    lines = ["| Step | Expected alert | Result | Detected in | Raised by / detail |",
             "| --- | --- | --- | --- | --- |"]
    for step in sequence.steps:
        detected = f"{step.detected_in_s} s" if step.detected_in_s is not None else "-"
        detail = ", ".join(step.raised_by) or step.detail or "-"
        lines.append(f"| {step.name} | {step.expect or '-'} | {step.state} | {detected} | {detail} |")
    return lines


def save_results(path, sequence, round_number, talk_time_s):
    """Append one round to the results file (created with a header the first time)."""
    finished = sequence.finished or utc_now()
    minutes, seconds = divmod(round((finished - sequence.started).total_seconds()), 60)
    lines = []
    if not path.exists():
        lines += [f"# Demo results: {sequence.started.astimezone():%Y-%m-%d %H:%M}", "",
                  f"Settings: agents report every {REPORT_INTERVAL_S} s, offline after "
                  f"{SERVER_SETTINGS['OFFLINE_THRESHOLD_S']} s, monitor sweep every {SERVER_SETTINGS['SWEEP_INTERVAL_S']} s, "
                  f"alerts expire after {SERVER_SETTINGS['ALERT_EXPIRY_S']} s, talk time {talk_time_s} s.", ""]
    lines += [f"## Round {round_number} ({sequence.started.astimezone():%H:%M:%S} to "
              f"{finished.astimezone():%H:%M:%S}, {minutes} min {seconds} s)", "",
              *results_table(sequence), "",
              "Unexpected alerts: " + (", ".join(sequence.unexpected) or "none"), "", ""]
    with open(path, "a", encoding="utf-8") as results:
        results.write("\n".join(lines))


def parse_args():
    parser = argparse.ArgumentParser(description="Start the whole system and run the attack sequence.")
    parser.add_argument("--talk", type=int, default=TALK_TIME_S,
                        help=f"seconds to pause after each detection (default {TALK_TIME_S})")
    parser.add_argument("--only", help=f"comma-separated attacks to run: {', '.join(STEP_KEYS)}")
    parser.add_argument("--loop", action="store_true", help="repeat the sequence until Ctrl+C")
    args = parser.parse_args()

    if args.talk < 0:
        parser.error("--talk cannot be negative")
    if args.only:
        chosen = [key.strip() for key in args.only.split(",") if key.strip()]
        unknown = [key for key in chosen if key not in STEP_KEYS]
        if unknown or not chosen:
            parser.error(f"unknown attack in --only: {', '.join(unknown) or '(none given)'}. "
                         f"Choose from: {', '.join(STEP_KEYS)}")
        args.only = set(chosen)
    return args


def chosen_steps(only):
    return [step for step in make_steps() if not only or step.key in only]


# ---------- Main ----------

def clear_old_data():
    """Start each demo with an empty database and login log."""
    for path in (DB_FILE, DB_FILE.with_name("monitor.db-wal"), DB_FILE.with_name("monitor.db-shm"),
                 AUTH_LOG, TIMELINE_FILE):
        path.unlink(missing_ok=True)


def start_everything(processes):
    processes.start("server", ["-m", "app"], cwd=ROOT / "server", env={
        **SERVER_SETTINGS,
        "HOST": "127.0.0.1",
        "PORT": "8000",
        "DB_PATH": str(DB_FILE),
        "TIMELINE_PATH": str(TIMELINE_FILE),
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
    args = parse_args()
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
        print(f"\nDashboard: {SERVER_URL}/\n")
        results = LOG_DIR / f"results-{datetime.now():%Y-%m-%d-%H%M}.md"
        last_seen_by_id = {}
        round_number = 1
        while True:
            sequence = Sequence(processes, chosen_steps(args.only), args.talk, last_seen_by_id)
            sequence.run()
            save_results(results, sequence, round_number, args.talk)
            print("\n" + "\n".join(results_table(sequence)))
            print("Unexpected alerts: " + (", ".join(sequence.unexpected) or "none"))
            print(f"Saved to {results.relative_to(ROOT)}\n")
            if not args.loop:
                break
            say(f"Round {round_number} finished. Next round in {args.talk} s.")
            sequence.wait(args.talk)
            round_number += 1

        say("Attack sequence finished. Press Ctrl+C to stop.")
        while True:
            sequence.watch()  # keep recording any later alerts until Ctrl+C
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        processes.stop_all()
        TIMELINE_FILE.unlink(missing_ok=True)
        print("Stopped.")


if __name__ == "__main__":
    try:
        main()
    except DemoError as error:
        print(f"\nError: {error}", file=sys.stderr)
        sys.exit(1)
