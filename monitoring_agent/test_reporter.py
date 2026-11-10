from reporter import send_report

# Test report using the team's JSON structure
test_report = {
    "agent_id": "agent-web-01",
    "timestamp": "2026-11-10T00:41:35Z",
    "traffic": {
        "bytes_in": 1000,
        "bytes_out": 500,
        "packets_in": 10,
        "interval_s": 10
    },
    "failed_logins": [],
    "services": []
}

# Use a local address where no server is expected to be running
server_url = "http://127.0.0.1:8765"

result = send_report(server_url, test_report)

print(f"Final result: {result}")