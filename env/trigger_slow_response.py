import argparse
import json
import time
import urllib.request


def control(base, path):
    with urllib.request.urlopen(f"{base}{path}", timeout=5) as response:
        return json.loads(response.read())


def main():
    parser = argparse.ArgumentParser(description="Make the target service slow")
    parser.add_argument("--control", default="http://127.0.0.1:9001")
    parser.add_argument("--ms", type=int, default=1500,
                        help="delay in milliseconds (keep under 3000; slower counts as down)")
    parser.add_argument("--seconds", type=int, default=30)
    args = parser.parse_args()

    print(control(args.control, f"/slow?ms={args.ms}"))
    print(f"Service is slow ({args.ms} ms) for {args.seconds}s. "
          "Expect a HIGH_LATENCY alert on the agent's next report.")
    try:
        time.sleep(args.seconds)
    finally:
        # Always restore normal speed, even if you press Ctrl+C.
        print(control(args.control, "/fast"))
        print("Back to normal speed.")


if __name__ == "__main__":
    main()