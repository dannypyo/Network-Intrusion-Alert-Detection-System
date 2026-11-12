import argparse
import json
import time
import urllib.error
import urllib.request

PASSWORDS = ["123456", "password", "qwerty", "letmein", "admin", "welcome",
             "monkey", "dragon", "iloveyou", "football"]


def try_login(target, ip, username, password):
    body = json.dumps({"username": username, "password": password}).encode()
    request = urllib.request.Request(
        f"{target}/login",
        data=body,
        headers={"Content-Type": "application/json", "X-Source-IP": ip},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code  # 401 means the login failed, which is what we want


def main():
    parser = argparse.ArgumentParser(description="Simulate a password-guessing attack")
    parser.add_argument("--target", default="http://127.0.0.1:9000")
    parser.add_argument("--ip", default="10.0.0.66", help="pretend attacker address")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--attempts", type=int, default=8)
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between attempts")
    args = parser.parse_args()

    print(f"Trying {args.attempts} wrong passwords for '{args.username}' from {args.ip}...")
    for i in range(args.attempts):
        password = PASSWORDS[i % len(PASSWORDS)]
        status = try_login(args.target, args.ip, args.username, password)
        print(f"  attempt {i + 1}: password '{password}' -> HTTP {status}")
        time.sleep(args.delay)

    print("Done. Failed logins were written to env/logs/auth.log.")


if __name__ == "__main__":
    main()