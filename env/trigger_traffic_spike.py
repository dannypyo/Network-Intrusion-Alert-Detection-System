import argparse
import threading
import time
import urllib.request


def download_loop(url, stop_at, totals, index):
    """Keep downloading until time runs out, counting the bytes."""
    while time.monotonic() < stop_at:
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                while True:
                    data = response.read(65536)
                    if not data:
                        break
                    totals[index] += len(data)
        except OSError as error:
            print(f"download failed: {error}")
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description="Create a burst of network traffic")
    parser.add_argument("--target", default="http://127.0.0.1:9000")
    parser.add_argument("--seconds", type=int, default=30,
                        help="keep this longer than the agent's report interval")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--mb", type=int, default=20, help="size of each download")
    args = parser.parse_args()

    url = f"{args.target}/big?mb={args.mb}"
    stop_at = time.monotonic() + args.seconds
    totals = [0] * args.threads

    print(f"Flooding {url} with {args.threads} threads for {args.seconds}s...")
    threads = [
        threading.Thread(target=download_loop, args=(url, stop_at, totals, i))
        for i in range(args.threads)
    ]
    for t in threads:
        t.start()

    # Print progress once a second.
    start = time.monotonic()
    while any(t.is_alive() for t in threads):
        time.sleep(1)
        elapsed = time.monotonic() - start
        mb = sum(totals) / 1_000_000
        print(f"  {elapsed:4.0f}s  {mb:8.1f} MB downloaded  ({mb / elapsed:6.1f} MB/s)")

    print("Done. Expect a TRAFFIC_SPIKE alert on the agent's next report.")


if __name__ == "__main__":
    main()