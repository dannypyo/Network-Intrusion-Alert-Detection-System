import socket
import time

# Maximum time to wait for a TCP connection
CONNECT_TIMEOUT_S = 2


def classify_connection_error(error):
    """
    Turn a failed connection into the error value the server expects.
    """
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, ConnectionRefusedError):
        return "refused"
    if isinstance(error, socket.gaierror):
        # The host name could not be looked up
        return "dns"
    return "unreachable"


def check_service_availability(host, port, timeout=CONNECT_TIMEOUT_S):
    """
    Check whether a service accepts a TCP connection.

    Args:
        host: Server hostname or IP address.
        port: Port the service is listening on.
        timeout: Maximum time to wait for a connection.

    Returns:
        {"up": bool, "response_ms": connect time or None, "error": reason or None}
    """

    start_time = time.perf_counter()

    try:
        # Attempt to establish a TCP connection
        with socket.create_connection((host, port), timeout=timeout):
            response_ms = (time.perf_counter() - start_time) * 1000
            return {"up": True, "response_ms": round(response_ms, 2), "error": None}

    except OSError as error:
        # Connection failed or the service could not be reached
        return {"up": False, "response_ms": None, "error": classify_connection_error(error)}
