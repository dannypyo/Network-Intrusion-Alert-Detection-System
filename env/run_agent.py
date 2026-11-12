import argparse
import os
import sys

# Folder that holds Danny's agent code (one level up, then monitoring_agent/).
AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "monitoring_agent")


def main():
    parser = argparse.ArgumentParser(description="Run the monitoring agent against the test environment")
    parser.add_argument("--agent-id", default="agent-test-01")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="where reports are sent")
    parser.add_argument("--interval", type=int, default=10, help="seconds between reports")
    parser.add_argument("--target-host", default="127.0.0.1")
    parser.add_argument("--target-port", type=int, default=9000)
    args = parser.parse_args()

    # Let Python find Danny's files (config.py, main.py, collectors/...).
    sys.path.insert(0, os.path.abspath(AGENT_DIR))

    # 1. Load Danny's config and replace the settings we care about.
    import config
    config.AGENT_ID = args.agent_id
    config.SERVER_URL = args.server
    config.REPORT_INTERVAL = args.interval
    config.MONITORED_SERVICES = [
        {
            "name": "target",
            "host": args.target_host,
            "port": args.target_port,
            "url": f"http://{args.target_host}:{args.target_port}/",
        }
    ]

    # 2. Now load Danny's main.py. It copies the settings above when it loads.
    import main as agent_main

    print(f"Agent {args.agent_id} -> reports to {args.server}, "
          f"watches {args.target_host}:{args.target_port}, every {args.interval}s", flush=True)
    try:
        agent_main.main()
    except KeyboardInterrupt:
        print(f"\nAgent {args.agent_id} stopped.")


if __name__ == "__main__":
    main()