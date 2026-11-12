# Tools

Owner: Nathan

## fake_agent.py

Simulates several agents sending valid reports to the server and injects one scenario at a time, so you can test the server and dashboard without the target service. It uses only the Python standard library.

```bash
python tools/fake_agent.py                                     # 3 healthy agents
python tools/fake_agent.py --scenario brute-force --target 2   # agent 2 is attacked for 45 seconds
python tools/fake_agent.py --scenario cycle                    # every scenario in turn, until Ctrl+C
```

Scenarios: `normal`, `brute-force`, `traffic-spike`, `slow`, `down`, `offline`, and `cycle`. Run it with `--help` for every option. The agents appear on the dashboard as `fake-agent-01`, `fake-agent-02`, and so on; delete `server/data/monitor.db` to clear them.
