import requests
import time


def send_report(server_url, report, max_attempts=3):
    """
    Send a JSON report to the FastAPI server.

    Retry if the server cannot be reached or returns
    a temporary server error.
    """

    for attempt in range(1, max_attempts + 1):

        try:
            response = requests.post(
                f"{server_url}/report",
                json=report,
                timeout=5
            )

            # Raise an exception for unsuccessful HTTP responses
            response.raise_for_status()

            print("Report successfully sent!")
            return True

        except requests.RequestException as error:
            print(f"Attempt {attempt} failed: {error}")

            # Do not retry permanent client errors (HTTP 4xx)
            if (
                isinstance(error, requests.HTTPError)
                and error.response is not None
                and 400 <= error.response.status_code < 500
            ):
                print("Client error: check the API URL or report format.")
                return False

            # Wait before retrying, but not after the final attempt
            if attempt < max_attempts:
                print("Retrying in 2 seconds...")
                time.sleep(2)

    print("All attempts failed. Report was not delivered.")
    return False
