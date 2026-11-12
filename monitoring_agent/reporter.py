import requests

# Maximum time to connect, and to wait for the server to answer
CONNECT_TIMEOUT_S = 2
READ_TIMEOUT_S = 3


def describe_validation_errors(response):
    """
    Turn the server's 422 answer into one line per rejected field.
    """
    try:
        details = response.json()["detail"]
        return [
            f"  {'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in details
        ]
    except (ValueError, KeyError, TypeError):
        # Not the usual FastAPI format, so show the raw answer instead
        return [f"  {response.text[:500]}"]


def send_report(server_url, report, token):
    """
    Send a JSON report to the FastAPI server once.

    A failed report is not retried: the next report, sent one interval
    later, replaces it with newer data.

    Returns:
        True if the server accepted the report, otherwise False.
    """

    try:
        response = requests.post(
            f"{server_url}/report",
            json=report,
            headers={"X-Agent-Token": token},
            timeout=(CONNECT_TIMEOUT_S, READ_TIMEOUT_S)
        )

    except requests.RequestException as error:
        print(f"Server unreachable ({type(error).__name__}); this report is skipped.")
        return False

    status = response.status_code

    if 200 <= status < 300:
        try:
            body = response.json()
            report_id = body.get("report_id") if isinstance(body, dict) else None
        except ValueError:
            report_id = None
        print(f"Report sent (report_id {report_id})." if report_id is not None else "Report sent.")
        return True

    if status == 401:
        print("Rejected: AGENT_TOKEN does not match the server's.")
    elif status == 422:
        print("Rejected as invalid:")
        for line in describe_validation_errors(response):
            print(line)
    elif status == 413:
        print("Rejected: report too large.")
    elif status >= 500:
        print(f"Server error {status}; this report is skipped.")
    else:
        print(f"Unexpected response {status}: {response.text[:200]}")

    return False
