"""GET endpoints: agents, alerts, metrics, the dashboard page, and the API docs."""

from datetime import datetime, timedelta, timezone

import pytest

from app.db import connect, save_alerts, store_report, to_db_time
from app.models import AlertSignal, Report
from tests.helpers import valid_report


@pytest.fixture
def db(client, settings):
    """A connection to the test app's database, which the client created at startup."""
    conn = connect(settings.db_path)
    yield conn
    conn.close()


def ago(seconds):
    """A stored-format time this many seconds before now (the /metrics window uses the real clock)."""
    return to_db_time(datetime.now(timezone.utc) - timedelta(seconds=seconds))


def receive(db, agent_id, received_at, bytes_in=1000, logins=0, web_up=True):
    """Store a report as if it arrived at received_at. Returns its report id."""
    report = valid_report()
    report["agent_id"] = agent_id
    report["traffic"]["bytes_in"] = bytes_in
    report["failed_logins"] = report["failed_logins"][:1] * logins
    report["services"] = [{"name": "web", "host": "web", "port": 80, "up": web_up,
                           "response_ms": 4.2 if web_up else None, "error": None if web_up else "refused"}]
    return store_report(db, Report.model_validate(report), received_at)[0]


def add_alert(db, key, signaled_at):
    save_alerts(db, [AlertSignal(key=key, type=key.split(":")[0], severity="LOW", agent_id=None, message="m")],
                signaled_at)


def bytes_in(response):
    return [entry["traffic"]["bytes_in"] for entry in response.json()]


# ---------- /agents ----------

def test_agents_empty_at_first(client):
    assert client.get("/agents").json() == []


def test_agents_sorted_with_exact_shape(client, db):
    seen = ago(5)
    receive(db, "agent-web-01", seen)
    receive(db, "agent-db-01", ago(3))
    with db:
        db.execute("INSERT INTO agents (agent_id, status) VALUES ('agent-new', 'pending')")

    agents = client.get("/agents").json()

    assert [agent["agent_id"] for agent in agents] == ["agent-db-01", "agent-new", "agent-web-01"]
    assert agents[1] == {"agent_id": "agent-new", "status": "pending", "first_seen": None, "last_seen": None}
    assert agents[2] == {"agent_id": "agent-web-01", "status": "online", "first_seen": seen, "last_seen": seen}


# ---------- /alerts ----------

def test_alerts_filters_and_order(client, db):
    add_alert(db, "OLD:x", ago(200))
    add_alert(db, "MID:x", ago(100))
    add_alert(db, "NEW:x", ago(10))
    with db:
        db.execute("UPDATE alerts SET status = 'resolved', resolved_at = ? WHERE key = 'OLD:x'", (ago(50),))

    def keys(query=""):
        return [alert["key"] for alert in client.get(f"/alerts{query}").json()]

    assert keys() == ["NEW:x", "MID:x"]
    assert keys("?status=resolved") == ["OLD:x"]
    assert keys("?status=all") == ["NEW:x", "MID:x", "OLD:x"]
    assert keys("?status=all&limit=1") == ["NEW:x"]

    assert set(client.get("/alerts").json()[0]) == {
        "id", "key", "type", "severity", "agent_id", "message", "status",
        "first_seen", "last_seen", "count", "resolved_at",
    }


@pytest.mark.parametrize("query", ["status=bogus", "limit=0", "limit=501"])
def test_alerts_bad_parameters(client, query):
    assert client.get(f"/alerts?{query}").status_code == 422


# ---------- /metrics ----------

def test_metrics_window_and_order(client, db):
    receive(db, "agent-web-01", ago(600), bytes_in=600)  # outside the default 300 s window
    for seconds in (250, 150, 50):
        receive(db, "agent-web-01", ago(seconds), bytes_in=seconds)
    receive(db, "agent-db-01", ago(100), bytes_in=100)

    response = client.get("/metrics")

    assert bytes_in(response) == [250, 150, 100, 50]  # oldest first
    assert bytes_in(client.get("/metrics?since_seconds=120")) == [100, 50]
    assert bytes_in(client.get("/metrics?since_seconds=900")) == [600, 250, 150, 100, 50]


def test_metrics_agent_filter_and_limit(client, db):
    for seconds in (250, 150, 50):
        receive(db, "agent-web-01", ago(seconds), bytes_in=seconds)
    receive(db, "agent-db-01", ago(100), bytes_in=100)

    assert bytes_in(client.get("/metrics?agent_id=agent-web-01")) == [250, 150, 50]
    assert bytes_in(client.get("/metrics?agent_id=agent-web-01&limit=2")) == [150, 50]  # newest two, oldest first
    assert client.get("/metrics?agent_id=nobody").json() == []


def test_metrics_entry_exact_shape(client, db):
    received_at = ago(30)
    report_id = receive(db, "agent-web-01", received_at, logins=3, web_up=False)

    [entry] = client.get("/metrics").json()

    assert entry == {
        "report_id": report_id,
        "agent_id": "agent-web-01",
        "received_at": received_at,
        "traffic": {"bytes_in": 1000, "bytes_out": 18820, "packets_in": 410, "packets_out": 300, "interval_s": 10.02},
        "failed_logins": 3,
        "services": [{"name": "web", "up": False, "response_ms": None, "error": "refused"}],
    }


@pytest.mark.parametrize("query", ["since_seconds=0", "since_seconds=86401", "limit=2001", "agent_id=bad%20id"])
def test_metrics_bad_parameters(client, query):
    assert client.get(f"/metrics?{query}").status_code == 422


# ---------- access, dashboard, docs ----------

@pytest.mark.parametrize("path", ["/agents", "/alerts", "/metrics"])
def test_reads_need_no_token(client, path):
    assert client.get(path).status_code == 200


def test_dashboard_is_served(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text.lstrip().startswith("<!DOCTYPE html>")


def test_missing_dashboard_returns_404(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.routes.DASHBOARD_FILE", tmp_path / "missing.html")

    response = client.get("/")

    assert response.status_code == 404
    assert response.json() == {"detail": "Dashboard not found"}


def test_api_docs_list_the_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert {"/agents", "/alerts", "/metrics", "/report"} <= set(paths)
    assert "/" not in paths
    assert client.get("/docs").status_code == 200
