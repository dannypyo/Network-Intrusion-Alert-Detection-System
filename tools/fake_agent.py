"""Fake agent simulator: sends contract-valid reports for several agents and injects events.

A development tool for testing the server, detection and dashboard without running real
agents. The real agent and the env/ scripts produce the real data for the demo.
Uses only the Python standard library.

Examples:
    python tools/fake_agent.py
    python tools/fake_agent.py --agents 3 --scenario brute-force --target 2
    python tools/fake_agent.py --scenario cycle
"""

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEV_AGENT_TOKEN = "dev-token-not-for-deployment"
ATTACKER_IP = "203.0.113.50"  # TEST-NET-3: reserved for documentation, never a real host
EVENTS = ["brute-force", "traffic-spike", "slow", "down", "offline"]
CYCLE_NORMAL_S = 60

# Ignore any proxy settings: this tool talks to a server you run yourself
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def build_report(agent_id, interval, scenario):
    """One contract-valid report. Healthy values vary a little but stay far below every threshold."""
    now = datetime.now(timezone.utc).isoformat()

    bytes_in = random.randint(20_000, 80_000)
    if scenario == "traffic-spike":
        bytes_in = 20_000_000

    service = {"name": "web", "host": "127.0.0.1", "port": 9000, "up": True,
               "response_ms": round(random.uniform(3, 30), 2), "error": None}
    if scenario == "slow":
        service["response_ms"] = round(random.uniform(1500, 2500), 2)
    elif scenario == "down":
        service.update(up=False, response_ms=None, error="refused")

    failed_logins = []
    if scenario == "brute-force":
        failed_logins = [{"user": random.choice(["admin", "root", "guest"]), "source_ip": ATTACKER_IP, "time": now}
                         for _ in range(3)]

    return {
        "agent_id": agent_id,
        "timestamp": now,
        "traffic": {"bytes_in": bytes_in, "bytes_out": bytes_in // 3,
                    "packets_in": bytes_in // 1000 + 1, "packets_out": bytes_in // 3000 + 1,
                    "interval_s": float(interval)},
        "failed_logins": failed_logins,
        "services": [service],
    }


def send(server, token, report):
    """POST one report and describe the server's answer in a few words."""
    request = urllib.request.Request(
        f"{server}/report", data=json.dumps(report).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Agent-Token": token},
    )
    try:
        with OPENER.open(request, timeout=5) as response:
            body = json.loads(response.read() or b"{}")
            return f"{response.status}, alerts: {body.get('alerts', '?')}"
    except urllib.error.HTTPError as error:
        return f"{error.code} {error.read()[:200].decode(errors='replace')}"
    except (urllib.error.URLError, OSError) as error:
        return f"unreachable ({error})"


def phases(scenario, duration):
    """Yield (scenario, seconds) for the target agent. None means 'until stopped'."""
    if scenario == "cycle":
        while True:
            for event in EVENTS:
                yield "normal", CYCLE_NORMAL_S
                yield event, duration
    else:
        if scenario != "normal":
            yield scenario, duration
        yield "normal", None


def main():
    parser = argparse.ArgumentParser(description="Simulate agents and inject detection scenarios.")
    parser.add_argument("--agents", type=int, default=3, help="number of fake agents (1-20)")
    parser.add_argument("--interval", type=int, default=10, help="seconds between reports")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="server address")
    parser.add_argument("--token", default=os.environ.get("AGENT_TOKEN") or DEV_AGENT_TOKEN,
                        help="agent token (default: AGENT_TOKEN, or the development token)")
    parser.add_argument("--scenario", default="normal", choices=["normal", *EVENTS, "cycle"])
    parser.add_argument("--target", type=int, default=1, help="which agent the scenario affects")
    parser.add_argument("--duration", type=int, default=45, help="seconds each scenario lasts")
    args = parser.parse_args()

    if not 1 <= args.agents <= 20:
        parser.error("--agents must be between 1 and 20")
    if not 1 <= args.target <= args.agents:
        parser.error(f"--target must be between 1 and {args.agents}")
    if args.interval < 1 or args.duration < 1:
        parser.error("--interval and --duration must be at least 1")

    server = args.server.rstrip("/")
    agents = [f"fake-agent-{n:02d}" for n in range(1, args.agents + 1)]
    target = agents[args.target - 1]
    timeline = phases(args.scenario, args.duration)

    def start_next_phase():
        scenario, seconds = next(timeline)
        print(f"== {target}: {scenario}" + (f" for {seconds} s" if seconds else ""), flush=True)
        return scenario, (time.monotonic() + seconds if seconds else None)

    print(f"Sending reports for {len(agents)} agents to {server} every {args.interval} s. Ctrl+C to stop.")
    scenario, phase_ends = start_next_phase()
    next_report_at = time.monotonic()

    try:
        while True:
            time.sleep(max(0, next_report_at - time.monotonic()))
            next_report_at = time.monotonic() + args.interval
            if phase_ends and time.monotonic() >= phase_ends:
                scenario, phase_ends = start_next_phase()

            stamp = datetime.now().strftime("%H:%M:%S")
            for agent_id in agents:
                agent_scenario = scenario if agent_id == target else "normal"
                if agent_scenario == "offline":
                    continue  # an offline agent simply stops sending
                result = send(server, args.token, build_report(agent_id, args.interval, agent_scenario))
                print(f"{stamp} {agent_id} [{agent_scenario}] -> {result}", flush=True)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
