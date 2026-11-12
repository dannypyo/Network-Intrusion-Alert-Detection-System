# NIDS Monitoring Agent

## Overview

This monitoring agent is part of our Network Intrusion Detection System (NIDS) project.

The agent collects network traffic information, checks service availability, measures response times, and sends the collected data to a central server as JSON reports.

## Features

- **Network Traffic:** Tracks incoming and outgoing bytes and packets.
- **Response Time:** Measures how long a server takes to respond to an HTTP request.
- **Service Availability:** Checks whether a service is reachable.
- **JSON Reporting:** Generates reports approximately every 10 seconds.
- **HTTP Communication:** Sends reports to the central server using HTTP POST.
- **Reliable Reporting:** Sends each report once; if one fails, the next report replaces it.

## Project Files

- `main.py` — Runs the monitoring agent and collects data.
- `config.py` — Stores agent settings and monitored services.
- `reporter.py` — Sends JSON reports to the server.
- `collectors/traffic.py` — Collects network traffic.
- `collectors/response.py` — Measures response times.
- `collectors/availability.py` — Checks service availability.
- `check_*.py` — Scripts for checking individual components by hand.
- `echo_server.py` — Prints each report it receives, for testing without the central server.

## Setup

Install the required libraries:

```bash
pip install -r requirements.txt
```

## Configuration

All settings are optional environment variables. With none set, the agent reports to a server on this computer and monitors that server's health check.

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_ID` | `agent-local` | This agent's name (letters, digits, `.`, `_`, `-`) |
| `SERVER_URL` | `http://127.0.0.1:8000` | Central server address |
| `AGENT_TOKEN` | `dev-token-not-for-deployment` | Shared secret; must match the server's |
| `REPORT_INTERVAL_S` | `10` | Seconds between reports |
| `SERVICES` | `server=http://127.0.0.1:8000/health` | Comma-separated `name=url` pairs to monitor |

In `SERVICES`, the URL's scheme picks the check: `http://` or `https://` for an HTTP check, `tcp://` for a TCP connection check (a port is required). For example:

```bash
AGENT_ID=agent-web-01 SERVICES="web=http://127.0.0.1:9000/,control=tcp://127.0.0.1:9001" python main.py
```

Invalid settings stop the agent at startup with a message naming the problem.

## Running the Agent

Start the agent:

```bash
python main.py
```

The agent will continuously collect data and attempt to send reports to the configured server.

Press `Ctrl + C` to stop it.

## Local Testing

To test without the central FastAPI server:

1. Run `python echo_server.py` in one terminal.
2. Run `SERVER_URL=http://127.0.0.1:8765 python main.py` in another terminal.
3. Check that the report is received successfully.

To test against a target service and trigger alerts, see `env/README.md`.

## Integration

The monitoring agent has been tested locally and is ready for integration.

The agent reports to the FastAPI server, authenticating with `AGENT_TOKEN`. The remaining step is the failed-login collector.