"""POST /report over HTTP: authentication, validation, size limit, and what gets stored."""

import pytest

from app.db import connect
from tests.helpers import changed, valid_report


def rows(settings, sql, *params):
    conn = connect(settings.db_path)
    try:
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def count(settings, table):
    return rows(settings, f"SELECT count(*) AS n FROM {table}")[0]["n"]


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_valid_report_is_stored(client, auth, settings):
    response = client.post("/report", json=valid_report(), headers=auth)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "report_id": 1, "alerts": 0}

    [agent] = rows(settings, "SELECT * FROM agents")
    assert agent["agent_id"] == "agent-web-01" and agent["status"] == "online"
    assert agent["first_seen"] == agent["last_seen"]

    [report] = rows(settings, "SELECT * FROM reports")
    assert report["packets_out"] == 300 and report["interval_s"] == 10.02
    assert report["agent_ts"] == "2026-11-10T01:14:56.897391Z"

    checks = rows(settings, "SELECT name, up, response_ms, error FROM service_checks ORDER BY id")
    assert checks == [
        {"name": "web", "up": 1, "response_ms": 42.1, "error": None},
        {"name": "ssh", "up": 0, "response_ms": None, "error": "refused"},
    ]


def test_login_time_is_stored_as_utc(client, auth, settings):
    client.post("/report", json=valid_report(), headers=auth)
    [login] = rows(settings, "SELECT user, source_ip, time FROM failed_logins")
    # Sent as 18:14:51 Denver time (-07:00)
    assert login == {"user": "admin", "source_ip": "172.18.0.5", "time": "2026-11-10T01:14:51.000000Z"}


@pytest.mark.parametrize("headers", [{}, {"X-Agent-Token": "wrong-token-0123456789"}], ids=["missing", "wrong"])
def test_bad_token_is_rejected(client, settings, headers):
    response = client.post("/report", json=valid_report(), headers=headers)
    assert response.status_code == 401
    assert count(settings, "reports") == 0


def test_token_is_checked_before_the_body(client):
    # Without a token, a caller must not learn anything about the report format
    response = client.post("/report", json={"agent_id": 5})
    assert response.status_code == 401


def test_invalid_report_names_the_field(client, auth, settings):
    response = client.post("/report", json=changed("services.0.port", "80"), headers=auth)

    assert response.status_code == 422
    locations = [error["loc"] for error in response.json()["detail"]]
    assert ["body", "services", 0, "port"] in locations
    assert count(settings, "agents") == 0 and count(settings, "reports") == 0


def test_oversized_body_is_refused(client, auth):
    headers = {**auth, "Content-Type": "application/json"}
    response = client.post("/report", content=b" " * 1_000_001, headers=headers)
    assert response.status_code == 413


def test_second_report_keeps_first_seen(client, auth, settings, monkeypatch):
    times = iter(["2026-11-10T01:00:00.000000Z", "2026-11-10T01:00:10.000000Z"])
    monkeypatch.setattr("app.routes.utc_now", lambda: next(times))

    client.post("/report", json=valid_report(), headers=auth)
    client.post("/report", json=valid_report(), headers=auth)

    [agent] = rows(settings, "SELECT first_seen, last_seen FROM agents")
    assert agent == {"first_seen": "2026-11-10T01:00:00.000000Z", "last_seen": "2026-11-10T01:00:10.000000Z"}
    assert count(settings, "reports") == 2
