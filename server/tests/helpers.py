"""Builders for test reports: a valid report, plus a tool to change one field at a time."""

import copy

VALID_REPORT = {
    "agent_id": "agent-web-01",
    "timestamp": "2026-11-10T01:14:56.897391+00:00",
    "traffic": {"bytes_in": 52344, "bytes_out": 18820, "packets_in": 410, "packets_out": 300, "interval_s": 10.02},
    "failed_logins": [
        # Denver time (-07:00), to check that it is stored as UTC
        {"user": "admin", "source_ip": "172.18.0.5", "time": "2026-11-09T18:14:51-07:00"},
    ],
    "services": [
        {"name": "web", "host": "web", "port": 80, "up": True, "response_ms": 42.1, "error": None},
        {"name": "ssh", "host": "ssh", "port": 22, "up": False, "response_ms": None, "error": "refused"},
    ],
}

REMOVE = object()  # marker: delete the field instead of setting it


def valid_report():
    """A fresh copy of a report the server accepts."""
    return copy.deepcopy(VALID_REPORT)


def changed(path, value):
    """A valid report with one field set, or removed with REMOVE. Paths look like 'services.0.port'."""
    report = valid_report()
    *parents, last = path.split(".")
    target = report
    for key in parents:
        target = target[int(key)] if isinstance(target, list) else target[key]
    if isinstance(target, list):
        last = int(last)
    if value is REMOVE:
        del target[last]
    else:
        target[last] = value
    return report
