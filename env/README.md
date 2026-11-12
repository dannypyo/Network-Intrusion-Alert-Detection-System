# Test environment

Owner: Fernando

Scripts that run a fake target service on your machine and trigger each detection scenario against it. Everything uses the Python standard library except the agent, which needs `pip install -r monitoring_agent/requirements.txt`.

## Starting the environment

Run each command from the repository root, in its own terminal, in this order:

1. **Target service:** `python env/target_service.py`
2. **Server**, one of:
    - Real server: `cd server && python -m app` (port 8000)
    - Mock server: `python env/mock_server.py` (port 8765; prints reports and alerts in its terminal)
3. **Agent:** `python env/run_agent.py`
    - With the mock server, add `--server http://127.0.0.1:8765`

The agent reports every 10 seconds. Leave all three running, then use a fourth terminal for the trigger scripts.

## Trigger scripts

| Script | What it does | Expected alert |
| --- | --- | --- |
| `trigger_failed_logins.py` | 8 wrong passwords from `10.0.0.66`, 0.5 s apart | `BRUTE_FORCE_LOGIN` (more than 5 within 60 s) |
| `trigger_traffic_spike.py` | Parallel large downloads for 30 s | `TRAFFIC_SPIKE` (over 1 MB/s) |
| `trigger_slow_response.py` | Adds 1500 ms to every response for 30 s | `HIGH_LATENCY` (over 1000 ms) |
| `trigger_service_down.py` | Refuses connections for 30 s, then recovers | `SERVICE_DOWN` (after 2 failed checks) |
| `trigger_agent_offline.py` | Starts a second agent, kills it after 20 s | `AGENT_OFFLINE` (about 30 s later) |

Run any of them with `--help` to see their options. When using the mock server, pass `--server http://127.0.0.1:8765` to `trigger_agent_offline.py`.

## Ports and files

| Port or file | Used for |
| --- | --- |
| 8000 | Real server |
| 8765 | Mock server |
| 9000 | Target service: what the agent monitors |
| 9001 | Target service control port: used by the trigger scripts |
| `env/logs/auth.log` | Failed logins written by the target service (not committed) |

The target service accepts one login, `admin` / `password123`. Every other attempt is logged as a failure. The traffic spike measures all of your computer's traffic, so a video call or large download can also cause it.
