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
- **Retry Handling:** Retries failed requests up to three times.

## Project Files

- `main.py` — Runs the monitoring agent and collects data.
- `config.py` — Stores agent settings and monitored services.
- `reporter.py` — Sends JSON reports to the server.
- `collectors/traffic.py` — Collects network traffic.
- `collectors/response.py` — Measures response times.
- `collectors/availability.py` — Checks service availability.
- `test_*.py` — Files used to test individual components.

## Setup

Install the required libraries:

```bash
pip install -r requirements.txt
```

Update `config.py` with the correct server address and services to monitor.

## Running the Agent

Start the agent:

```bash
python main.py
```

The agent will continuously collect data and attempt to send reports to the configured server.

Press `Ctrl + C` to stop it.

## Local Testing

To test without the central FastAPI server:

1. Change `SERVER_URL` in `config.py` to `http://127.0.0.1:8765`.
2. Run `python test_server.py` in one terminal.
3. Run `python main.py` in another terminal.
4. Check that the report is received successfully.

## Integration

The monitoring agent has been tested locally and is ready for integration.

The remaining steps are connecting to the FastAPI server and adding failed-login collector.