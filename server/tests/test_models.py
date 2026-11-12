"""The agent report contract, tested directly against the Pydantic models."""

import json

import pytest
from pydantic import ValidationError

from app.models import Report
from tests.helpers import REMOVE, changed, valid_report

# FastAPI may validate from raw JSON or from an already-parsed dict, so every case runs both ways
MODES = ["json", "dict"]


def validate(report, mode):
    if mode == "json":
        return Report.model_validate_json(json.dumps(report))
    return Report.model_validate(report)


def many_services(count):
    report = valid_report()
    report["services"] = [dict(report["services"][0], name=f"svc{i}") for i in range(count)]
    return report


def many_logins(count):
    report = valid_report()
    report["failed_logins"] = report["failed_logins"] * count
    return report


ACCEPTED = {
    "valid report": valid_report(),
    "whole-number interval_s": changed("traffic.interval_s", 10),
    "IPv6 source_ip": changed("failed_logins.0.source_ip", "::1"),
    "Z timestamp": changed("timestamp", "2026-11-10T01:14:56Z"),
    "error key left out when healthy": changed("services.0.error", REMOVE),
    "no failed logins or services": {**valid_report(), "failed_logins": [], "services": []},
    "exactly 1000 failed logins": many_logins(1000),
    "exactly 50 services": many_services(50),
}


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("report", ACCEPTED.values(), ids=ACCEPTED.keys())
def test_accepted(report, mode):
    validate(report, mode)


# (description, report, where the error must point)
REJECTED = [
    ("extra top-level field", changed("extra", 1), ("extra",)),
    ("extra traffic field", changed("traffic.packets_dropped", 1), ("traffic", "packets_dropped")),
    ("extra service field", changed("services.0.status_code", 200), ("services", 0, "status_code")),
    ("extra login field", changed("failed_logins.0.port", 22), ("failed_logins", 0, "port")),
    ("missing packets_out", changed("traffic.packets_out", REMOVE), ("traffic", "packets_out")),
    ("missing response_ms key", changed("services.0.response_ms", REMOVE), ("services", 0, "response_ms")),
    ("port as text", changed("services.0.port", "80"), ("services", 0, "port")),
    ("port as 3.0", changed("services.0.port", 3.0), ("services", 0, "port")),
    ("port above 65535", changed("services.0.port", 70000), ("services", 0, "port")),
    ("port 0", changed("services.0.port", 0), ("services", 0, "port")),
    ("up as text", changed("services.0.up", "true"), ("services", 0, "up")),
    ("negative bytes", changed("traffic.bytes_in", -1), ("traffic", "bytes_in")),
    ("interval_s of 0", changed("traffic.interval_s", 0), ("traffic", "interval_s")),
    ("negative response_ms", changed("services.0.response_ms", -1.0), ("services", 0, "response_ms")),
    ("agent_id with a space", changed("agent_id", "web agent"), ("agent_id",)),
    ("agent_id with HTML", changed("agent_id", "<script>"), ("agent_id",)),
    ("agent_id over 64 characters", changed("agent_id", "a" * 65), ("agent_id",)),
    ("timestamp without timezone", changed("timestamp", "2026-11-10T01:14:56"), ("timestamp",)),
    ("login time without timezone", changed("failed_logins.0.time", "2026-11-10T01:14:56"), ("failed_logins", 0, "time")),
    ("hostname as source_ip", changed("failed_logins.0.source_ip", "attacker.local"), ("failed_logins", 0, "source_ip")),
    ("username over 128 characters", changed("failed_logins.0.user", "x" * 129), ("failed_logins", 0, "user")),
    ("empty username", changed("failed_logins.0.user", ""), ("failed_logins", 0, "user")),
    ("error outside the list", changed("services.1.error", "timed out"), ("services", 1, "error")),
    ("4xx as an error", changed("services.1.error", "http_404"), ("services", 1, "error")),
    ("up with an error", changed("services.0.error", "timeout"), ("services", 0)),
    ("up without a response time", changed("services.0.response_ms", None), ("services", 0)),
    ("down without an error", changed("services.1.error", None), ("services", 1)),
    ("duplicate service names", changed("services.1.name", "web"), ()),
    ("51 services", many_services(51), ("services",)),
    ("1001 failed logins", many_logins(1001), ("failed_logins",)),
]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("report, location", [(r, loc) for _, r, loc in REJECTED], ids=[name for name, _, _ in REJECTED])
def test_rejected(report, location, mode):
    with pytest.raises(ValidationError) as caught:
        validate(report, mode)
    assert caught.value.errors()[0]["loc"][:len(location)] == location


@pytest.mark.parametrize("literal", ["NaN", "Infinity"])
def test_non_finite_response_time_rejected(literal):
    # Python's JSON parser accepts these non-standard literals, so they must be rejected explicitly.
    # Infinity matters most: it would pass the ">= 0" check on its own.
    raw = json.dumps(valid_report()).replace("42.1", literal)
    with pytest.raises(ValidationError):
        Report.model_validate_json(raw)
    with pytest.raises(ValidationError):
        Report.model_validate(json.loads(raw))
