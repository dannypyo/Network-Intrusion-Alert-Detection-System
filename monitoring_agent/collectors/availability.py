import socket


def check_service_availability(host, port, timeout=3):
    """
    Check whether a service accepts a TCP connection.

    Args:
        host: Server hostname or IP address.
        port: Port the service is listening on.
        timeout: Maximum time to wait for a connection.

    Returns:
        True if the connection succeeds, False otherwise.
    """

    try:
        # Attempt to establish a TCP connection
        with socket.create_connection((host, port), timeout=timeout):
            return True

    except (socket.timeout, OSError):
        # Connection failed or the service could not be reached
        return False