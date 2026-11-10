# Unique identifier for this monitoring agent
AGENT_ID = "agent-web-01"

# FastAPI server address
# Change to http://127.0.0.1:8765 for local testing
SERVER_URL = "http://127.0.0.1:8000"

# How often the agent sends reports (seconds)
REPORT_INTERVAL = 10

# Services that the agent monitors
MONITORED_SERVICES = [
    {
        "name": "google",
        "host": "google.com",
        "port": 443,
        "url": "https://google.com"
    }
]