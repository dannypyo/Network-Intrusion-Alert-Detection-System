"""Detection through POST /report, and alert deduplication."""

import logging
import threading
from types import SimpleNamespace

from app.db import connect, init_db, save_alerts
from app.models import AlertSignal
from tests.helpers import valid_report


def report_with(web_up=True, web_ms=42.1, logins=0):
    """A valid report with one service, "web", and the chosen number of failed logins."""
    report = valid_report()
    report["services"] = [{"name": "web", "host": "web", "port": 80, "up": web_up,
                           "response_ms": web_ms, "error": None if web_up else "refused"}]
    report["failed_logins"] = report["failed_logins"][:1] * logins
    return report


def post(client, auth, report):
    response = client.post("/report", json=report, headers=auth)
    assert response.status_code == 200, response.text
    return response.json()


def alerts(settings):
    conn = connect(settings.db_path)
    try:
        return [dict(row) for row in conn.execute(
            "SELECT key, type, severity, status, count, message FROM alerts ORDER BY id")]
    finally:
        conn.close()


def signal(key, severity="HIGH"):
    return AlertSignal(key=key, type=key.split(":")[0], severity=severity, agent_id=None, message="test")


def test_service_down_needs_two_checks_then_repeats_are_counted(client, auth, settings):
    down = report_with(web_up=False, web_ms=None)

    assert post(client, auth, down)["alerts"] == 0
    assert post(client, auth, down)["alerts"] == 1
    assert post(client, auth, down)["alerts"] == 1

    [alert] = alerts(settings)
    assert alert["key"] == "SERVICE_DOWN:agent-web-01:web"
    assert (alert["severity"], alert["status"], alert["count"]) == ("HIGH", "active", 2)


def test_repeated_alert_shows_the_latest_message(client, auth, settings):
    post(client, auth, report_with(web_ms=1500.0))
    post(client, auth, report_with(web_ms=2500.0))

    [alert] = alerts(settings)
    assert alert["key"] == "HIGH_LATENCY:agent-web-01:web" and alert["count"] == 2
    assert "2500.0ms" in alert["message"]


def test_one_brute_force_alert_per_report(client, auth, settings):
    assert post(client, auth, report_with(logins=6))["alerts"] == 1

    [alert] = alerts(settings)
    assert alert["key"] == "BRUTE_FORCE_LOGIN:agent-web-01:172.18.0.5" and alert["count"] == 1


def test_engine_crash_keeps_the_report(client, auth, settings, monkeypatch, caplog):
    def crash(report):
        raise RuntimeError("bug in a rule")
    monkeypatch.setattr(client.app.state, "detection_engine", SimpleNamespace(evaluate_report=crash))

    assert post(client, auth, report_with())["alerts"] == 0

    conn = connect(settings.db_path)
    assert conn.execute("SELECT count(*) FROM reports").fetchone()[0] == 1
    conn.close()
    assert "Detection failed" in caplog.text


def test_malformed_alert_is_skipped(client, auth, settings, monkeypatch, caplog):
    engine_output = [
        {"key": "BAD:agent-web-01", "type": "BAD", "severity": "CRITICAL", "agent_id": "agent-web-01", "message": "m"},
        {"key": "GOOD:agent-web-01", "type": "GOOD", "severity": "LOW", "agent_id": "agent-web-01", "message": "m"},
    ]
    monkeypatch.setattr(client.app.state, "detection_engine",
                        SimpleNamespace(evaluate_report=lambda report: engine_output))

    assert post(client, auth, report_with())["alerts"] == 1
    assert [alert["key"] for alert in alerts(settings)] == ["GOOD:agent-web-01"]
    assert "Skipping malformed alert" in caplog.text


def test_concurrent_saves_make_one_alert(settings):
    init_db(settings.db_path)
    start_together = threading.Barrier(20)
    errors = []

    def save(n):
        conn = connect(settings.db_path)
        try:
            start_together.wait()
            save_alerts(conn, [signal("RACE:x")], f"2026-11-11T12:00:{n:02d}.000000Z")
        except Exception as error:
            errors.append(error)
        finally:
            conn.close()

    threads = [threading.Thread(target=save, args=(n,)) for n in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    [alert] = alerts(settings)
    assert alert["count"] == 20


def test_resolved_key_starts_a_new_alert(settings):
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    save_alerts(conn, [signal("SERVICE_DOWN:x")], "2026-11-11T12:00:00.000000Z")
    with conn:
        conn.execute("UPDATE alerts SET status = 'resolved'")
    save_alerts(conn, [signal("SERVICE_DOWN:x")], "2026-11-11T12:05:00.000000Z")
    conn.close()

    assert [(a["status"], a["count"]) for a in alerts(settings)] == [("resolved", 1), ("active", 1)]
