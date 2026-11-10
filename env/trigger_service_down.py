python


import argparse
import json
import time
import urllib.request


def control(base, path):
    with urllib.request.urlopen(f"{base}{path}", timeout=5) as response:
        return json.loads(response.read())


def main():
    parser = argparse.ArgumentParser(description="Take the target service offline")
    parser.add_argument("--control", default="http://127.0.0.1:9001")
    parser.add_argument("--seconds", type=int, default=30,
                        help="must be more than 2 agent report intervals")
    args = parser.parse_args()

    print(control(args.control, "/down"))
    print(f"Service is DOWN for {args.seconds}s. "
          "Expect a SERVICE_DOWN alert after the agent's 2nd failed check.")
    try:
        time.sleep(args.seconds)
    finally:
        # Always bring it back, even if you press Ctrl+C.
        print(control(args.control, "/up"))
        print("Service is back UP.")


if __name__ == "__main__":
    main()