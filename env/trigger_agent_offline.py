python
"""
Scenario: AGENT_OFFLINE

Starts a separate agent ("agent-offline-test"), lets it send a few
reports, then kills it as if the computer crashed. The server should
mark it offline after OFFLINE_THRESHOLD_S (30 s by default).

Run it (target_service.py and a server must be running):
    python trigger_agent_offline.py
    python trigger_agent_offline.py --server http://127.0.0.1:8765   # mock server
"""

import argparse
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(description="Start an agent, then kill it")
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--agent-id", default="agent-offline-test")
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--run-seconds", type=int, default=20, help="how long the agent runs first")
    parser.add_argument("--threshold", type=int, default=30, help="server's OFFLINE_THRESHOLD_S")
    args = parser.parse_args()

    command = [sys.executable, os.path.join(HERE, "run_agent.py"),
               "--agent-id", args.agent_id, "--server", args.server,
               "--interval", str(args.interval)]

    print(f"Starting {args.agent_id} for {args.run_seconds}s...")
    agent = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(args.run_seconds)

    agent.kill()  # sudden stop, like pulling the plug
    agent.wait()
    print(f"Killed {args.agent_id}. The server should mark it offline in about "
          f"{args.threshold}s.")

    wait = args.threshold + 10
    for left in range(wait, 0, -5):
        print(f"  waiting... {left}s")
        time.sleep(5)
    print(f"Done. {args.agent_id} should now show as offline.")


if __name__ == "__main__":
    main()