import socket
import time

import requests

from collectors.availability import classify_connection_error

# Maximum time to connect, and to wait for the server to start answering
CONNECT_TIMEOUT_S = 2
READ_TIMEOUT_S = 3


def find_root_cause(error):
    """
    requests wraps the real socket error several layers deep.
    Search the wrapped exceptions for the one that explains the failure.
    """
    to_check = [error]
    seen = set()

    while to_check:
        current = to_check.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))

        if isinstance(current, (TimeoutError, ConnectionRefusedError, socket.gaierror)):
            return current

        wrapped = (current.__cause__, current.__context__, getattr(current, "reason", None), *current.args)
        to_check.extend(e for e in wrapped if isinstance(e, BaseException))

    return error


def get_response_time(url):
    """
    Check an HTTP service and measure how long it takes to start responding.

    The time stops when the status and headers arrive, so it measures the
    server, not the size of the page. A 5xx status counts as down.

    Returns:
        {"up": bool, "response_ms": time or None, "error": reason or None}
    """

    try:
        # Record the starting time
        start_time = time.perf_counter()

        # stream=True returns as soon as the headers arrive, without downloading the body
        response = requests.get(
            url,
            timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S),
            allow_redirects=False,
            stream=True
        )

        # Calculate elapsed time in milliseconds
        response_ms = round((time.perf_counter() - start_time) * 1000, 2)
        response.close()

    except requests.Timeout:
        return {"up": False, "response_ms": None, "error": "timeout"}

    except requests.RequestException as error:
        root_cause = find_root_cause(error)
        return {"up": False, "response_ms": None, "error": classify_connection_error(root_cause)}

    # The server answered, but a 5xx status means it is failing
    if 500 <= response.status_code <= 599:
        return {"up": False, "response_ms": response_ms, "error": f"http_{response.status_code}"}

    return {"up": True, "response_ms": response_ms, "error": None}
