from app.detection import DetectionEngine

engine = DetectionEngine()

# Mock report 1: Normal report
report_normal = {
    "agent_id": "agent-web-01",
    "timestamp": "2026-10-22T14:30:00Z",
    "traffic": {"bytes_in": 1000, "bytes_out": 500, "packets_in": 10, "interval_s": 10},
    "failed_logins": [],
    "services": [{"name": "web", "host": "web", "port": 80, "up": True, "response_ms": 42.1}]
}

# Mock report 2: Brute-force login attack + Service down
report_attack = {
    "agent_id": "agent-web-01",
    "timestamp": "2026-10-22T14:30:10Z",
    "traffic": {"bytes_in": 2000000, "bytes_out": 500, "packets_in": 100, "interval_s": 10},
    "failed_logins": [
        {"user": "admin", "source_ip": "172.18.0.5", "time": "2026-10-22T14:30:01Z"},
        {"user": "root", "source_ip": "172.18.0.5", "time": "2026-10-22T14:30:03Z"},
        {"user": "user", "source_ip": "172.18.0.5", "time": "2026-10-22T14:30:05Z"},
        {"user": "test", "source_ip": "172.18.0.5", "time": "2026-10-22T14:30:07Z"},
        {"user": "guest", "source_ip": "172.18.0.5", "time": "2026-10-22T14:30:09Z"},
        {"user": "oracle", "source_ip": "172.18.0.5", "time": "2026-10-22T14:30:10Z"}
    ],
    "services": [{"name": "web", "host": "web", "port": 80, "up": False, "response_ms": 1200.0}]
}

print("--- Testing Normal Report ---")
print(engine.evaluate_report(report_normal))

print("\n--- Testing Attack Report (First Check) ---")
alerts_1 = engine.evaluate_report(report_attack)
for a in alerts_1:
    print(a)

print("\n--- Testing Attack Report (Second Check: the same alerts repeat; the server deduplicates them by key) ---")
report_attack["timestamp"] = "2026-10-22T14:30:20Z"
alerts_2 = engine.evaluate_report(report_attack)
for a in alerts_2:
    print(a)