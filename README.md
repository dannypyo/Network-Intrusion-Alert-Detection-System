# Network Intrusion Detection and Alert System

CS 3700 group project. Monitoring agents collect network and system data and report it over HTTP to a central FastAPI server. The server stores reports in SQLite, runs rule-based detection, flags agents that stop reporting, and shows alerts on a web dashboard.

## Repository layout

| Folder | Contents | Owner |
| --- | --- | --- |
| `server/` | FastAPI server, SQLite storage, offline-agent detection | Nathan |
| `server/app/detection.py` | Detection rules | Matthew |
| `dashboard/` | Web dashboard (served by the server) | Matthew |
| `monitoring_agent/` | Agent: traffic, response time, availability, failed logins | Danny |
| `env/` | Test environment and event trigger scripts | Fernando |
| `tools/` | Development tools, such as the fake agent | Nathan |
| `docs/` | Agent/server protocol reference | Nathan |

How agents and the server communicate is described in `docs/protocol.md`.

## Quick start (Linux or WSL)

Requires Python 3.11 or newer. On Ubuntu or WSL, if `python3 -m venv` fails, install the venv package once with `sudo apt install python3-venv`.

### 1. Set up (once)

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r server/requirements-dev.txt -r monitoring_agent/requirements.txt
```

Run `source .venv/bin/activate` again in every new terminal. On Windows PowerShell, use `.venv\Scripts\Activate.ps1` instead.

### 2. Run the system

Start each of these in its own terminal, from the repository root, in this order:

```bash
cd server && python -m app        # terminal 1: the server, on port 8000
python env/target_service.py      # terminal 2: the service the agent monitors
python env/run_agent.py           # terminal 3: an agent that reports every 10 seconds
```

Open http://127.0.0.1:8000/ for the dashboard and http://127.0.0.1:8000/docs for the API reference. The agent appears as `online` within 10 seconds. For development with auto-reload, run `uvicorn app.main:app --reload` from `server/` instead of `python -m app`.

### 3. Trigger an alert

In a fourth terminal:

```bash
python env/trigger_failed_logins.py
```

A `BRUTE_FORCE_LOGIN` alert appears on the dashboard within about 10 seconds. `env/README.md` lists all five scenarios and the alert each one causes.

### 4. Run the tests

```bash
cd server && pytest
```

### Without the target service

`python tools/fake_agent.py --scenario cycle` simulates three agents and cycles through every alert, so you can test the server and dashboard alone. See `tools/README.md`.

### Starting over

Stop everything with Ctrl+C. To clear all stored agents and alerts, delete the database with `rm -f server/data/monitor.db*`.

### More documentation

- `docs/protocol.md`: how agents and the server communicate, the detection rules, and the security measures
- `env/README.md`: the test environment and its scenarios
- `monitoring_agent/README.md`: agent settings

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
| `TIMELINE_PATH` | `demo_logs/timeline.json` | Status file written by `demo.py`, served at `GET /timeline` |
