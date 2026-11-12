# Network Intrusion Detection and Alert System

CS 3700 group project. Monitoring agents collect network and system data and report it over HTTP to a central FastAPI server. The server stores reports in SQLite, runs rule-based detection, flags agents that stop reporting, and shows alerts on a web dashboard.

## Repository layout

| Folder | Contents | Owner |
| --- | --- | --- |
| `server/` | FastAPI server, SQLite storage, offline-agent detection | Nathan |
| `server/app/detection.py` | Detection rules | Matthew |
| `dashboard/` | Web dashboard (served by the server) | Matthew |
| `monitoring_agent/` | Agent: traffic, response time, availability | Danny |
| `env/` | Test environment and event trigger scripts | Fernando |
| `tools/` | Development tools, such as the fake agent | Nathan |
| `docs/` | Agent/server contract | Nathan |

The report format, endpoints, and detection interface are defined in `docs/contract.md`.

## Running the server

Requires Python 3.10 or newer.

```bash
cd server
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app
```

Check it at http://127.0.0.1:8000/health. For development with auto-reload, run `uvicorn app.main:app --reload` from `server/` instead.

## Server configuration

All settings are optional environment variables.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DB_PATH` | `data/monitor.db` | SQLite file, relative to where the server starts |
| `HOST` | `127.0.0.1` | Address to listen on (`0.0.0.0` in Docker) |
| `PORT` | `8000` | Port to listen on |
| `OFFLINE_THRESHOLD_S` | `30` | Seconds without a report before an agent is offline |
| `SWEEP_INTERVAL_S` | `5` | How often the server checks for offline agents |
| `ALERT_EXPIRY_S` | `60` | Seconds without a new signal before an alert resolves |
| `AGENT_TOKEN` | `dev-token-not-for-deployment` | Shared secret agents send in `X-Agent-Token`. Set your own (16+ characters) before deploying |
| `EXPECTED_AGENTS` | (none) | Comma-separated agent IDs that should be reporting; any that never report are flagged offline |