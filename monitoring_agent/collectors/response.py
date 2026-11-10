import requests
import time


def get_response_time(url):
    """
    Measure how long a server takes to respond to an HTTP request.

    Returns:
        Response time in milliseconds, or None if the request fails.
    """

    try:
        # Record the starting time
        start_time = time.perf_counter()

        # Send an HTTP GET request
        response = requests.get(url, timeout=5)

        # Record the ending time
        end_time = time.perf_counter()

        # Calculate elapsed time in milliseconds
        response_ms = (end_time - start_time) * 1000

        return round(response_ms, 2)

    except requests.RequestException:
        # Return None if the server cannot be reached
        return None