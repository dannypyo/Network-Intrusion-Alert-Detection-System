import json
import time
from datetime import datetime, timezone
from reporter import send_report
from config import SERVER_URL, AGENT_TOKEN

# Import our configuration settings
from config import AGENT_ID, REPORT_INTERVAL, MONITORED_SERVICES

# Import the collectors we created
from collectors.traffic import (
    get_network_snapshot,
    calculate_network_traffic
)
from collectors.response import get_response_time
from collectors.availability import check_service_availability


def collect_report(previous_stats, current_stats, interval_s):
    """
    Collect monitoring data and build a report.
    """

    # Calculate network traffic since the previous snapshot
    traffic = calculate_network_traffic(previous_stats, current_stats)

    # Include the measurement interval in the traffic data
    traffic["interval_s"] = round(interval_s, 2)

    # Store information about monitored services
    services = []

    # Check each service listed in config.py
    for service in MONITORED_SERVICES:

        # One check per service: HTTP if it has a URL, otherwise a TCP connection
        if service.get("url"):
            result = get_response_time(service["url"])
        else:
            result = check_service_availability(
                service["host"],
                service["port"]
            )

        # Add this service's results to the list
        services.append({
            "name": service["name"],
            "host": service["host"],
            "port": service["port"],
            "up": result["up"],
            "response_ms": result["response_ms"],
            "error": result["error"]
        })

    # Assemble the report using the team's JSON structure
    report = {
        "agent_id": AGENT_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "traffic": traffic,
        "failed_logins": [],
        "services": services
    }

    return report



def main():
    print(f"Starting monitoring agent: {AGENT_ID}")

    # Take the first network snapshot
    previous_stats = get_network_snapshot()
    previous_time = time.monotonic()
    next_report_at = previous_time + REPORT_INTERVAL

    # Keep the agent running
    while True:

        # Wait until the next report is due. The checks and the send take time,
        # so this keeps reports one interval apart instead of drifting later.
        time.sleep(max(0, next_report_at - time.monotonic()))
        next_report_at = time.monotonic() + REPORT_INTERVAL

        # Take the next snapshot
        current_stats = get_network_snapshot()
        current_time = time.monotonic()

        # Calculate the elapsed time
        interval_s = current_time - previous_time

        # Generate a monitoring report
        report = collect_report(
            previous_stats,
            current_stats,
            interval_s
        )

        # Display the report
        print(json.dumps(report, indent=4), flush=True)

        # Save the snapshot for the next interval
        previous_stats = current_stats
        previous_time = current_time

        success = send_report(SERVER_URL, report, AGENT_TOKEN)

        if not success:
            print("Report delivery failed. Continuing monitoring...")


if __name__ == "__main__":
    main()