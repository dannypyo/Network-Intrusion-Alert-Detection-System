"""The background monitor: startup reset, offline detection, coming back, and alert expiry."""

import asyncio
import dataclasses
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.monitor as monitor
from app.db import connect, init_db, prepare_agents, save_alerts, store_report, sweep, to_db_time
from app.main import create_app
from app.models import AlertSignal, Report
from tests.helpers import valid_report

START = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def at(seconds):
    """A time measured in seconds from START."""
    return START + timedelta(seconds=seconds)


@pytest.fixture
def conn(settings):
    init_db(settings.db_path)
    connection = connect(settings.db_path)
    yield connection
    connection.close()


def add_agent(conn, agent_id, status, last_seen=None):
    with conn:
        conn.execute("INSERT INTO agents VALUES (?, ?, ?, ?)", (agent_id, status, last_seen, last_seen))


def statuses(conn):
    return dict(conn.execute("SELECT agent_id, status FROM agents").fetchall())


def active_alerts(conn):
    return {row["key"]: row["message"] for row in conn.execute("SELECT key, message FROM alerts WHERE status = 'active'")}


def run_sweep(conn, seconds, started=0):
    """Sweep at START + seconds, as if the server started at START + started (30 s offline, 60 s expiry)."""
    return sweep(conn, at(seconds), at(started), 30, 60)


def receive(conn, agent_id, seconds):
    report = Report.model_validate({**valid_report(), "agent_id": agent_id, "failed_logins": [], "services": []})
    return store_report(conn, report, to_db_time(at(seconds)))


def test_prepare_agents(conn):
    add_agent(conn, "was-online", "online", to_db_time(at(-600)))
    add_agent(conn, "was-offline", "offline", to_db_time(at(-900)))

    prepare_agents(conn, ("agent-db-01", "was-online"))

    assert statuses(conn) == {"was-online": "pending", "was-offline": "offline", "agent-db-01": "pending"}


def test_grace_period_after_restart(conn):
    add_agent(conn, "agent-web-01", "online", to_db_time(at(-600)))
    prepare_agents(conn, ())

    assert run_sweep(conn, 20) == ([], 0)
    assert run_sweep(conn, 31) == (["agent-web-01"], 0)
    assert "last report 2026-11-11T11:50:00.000000Z" in active_alerts(conn)["AGENT_OFFLINE:agent-web-01"]


def test_silent_agent_goes_offline_after_30_seconds(conn):
    receive(conn, "agent-web-01", 0)

    assert run_sweep(conn, 29, started=-100) == ([], 0)
    assert run_sweep(conn, 31, started=-100) == (["agent-web-01"], 0)
    assert statuses(conn)["agent-web-01"] == "offline"


def test_expected_agent_that_never_reports(conn):
    prepare_agents(conn, ("agent-db-01",))

    run_sweep(conn, 31)

    assert active_alerts(conn) == {"AGENT_OFFLINE:agent-db-01": "agent-db-01 has not reported since the server started"}


def test_offline_agent_is_not_flagged_again(conn):
    receive(conn, "agent-web-01", 0)
    run_sweep(conn, 31)

    assert run_sweep(conn, 36) == ([], 0)
    assert run_sweep(conn, 600) == ([], 0)
    assert tuple(conn.execute("SELECT count(*), max(count) FROM alerts").fetchone()) == (1, 1)


def test_offline_agent_comes_back(client, auth, settings, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    report = {**valid_report(), "services": []}  # no services, so no other alerts appear
    client.post("/report", json=report, headers=auth)
    conn = connect(settings.db_path)
    now = datetime.now(timezone.utc)
    sweep(conn, now + timedelta(seconds=31), now - timedelta(seconds=100), 30, 60)
    assert statuses(conn)["agent-web-01"] == "offline"

    client.post("/report", json=report, headers=auth)
    client.post("/report", json=report, headers=auth)

    assert statuses(conn)["agent-web-01"] == "online"
    assert active_alerts(conn) == {}
    conn.close()
    assert caplog.text.count("agent-web-01 is back online") == 1


def test_sweep_logs_agents_going_offline(conn, settings, caplog):
    add_agent(conn, "agent-web-01", "online", to_db_time(datetime.now(timezone.utc) - timedelta(minutes=10)))

    monitor.sweep_once(settings, datetime.now(timezone.utc) - timedelta(minutes=5))

    assert "agent-web-01 is offline" in caplog.text


def test_alert_expiry(conn):
    receive(conn, "agent-web-01", 0)
    run_sweep(conn, 31)  # raises AGENT_OFFLINE
    save_alerts(conn, [AlertSignal(key="SERVICE_DOWN:agent-web-01:web", type="SERVICE_DOWN",
                                   severity="HIGH", agent_id="agent-web-01", message="down")], to_db_time(at(100)))

    assert run_sweep(conn, 159) == ([], 0)
    assert run_sweep(conn, 161) == ([], 1)
    assert run_sweep(conn, 10_000) == ([], 0)
    assert list(active_alerts(conn)) == ["AGENT_OFFLINE:agent-web-01"]  # never expires


def test_monitor_survives_a_failed_sweep(settings, monkeypatch, caplog):
    init_db(settings.db_path)
    calls = []
    real_sweep_once = monitor.sweep_once

    def flaky_sweep(settings, started_at):
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        real_sweep_once(settings, started_at)

    monkeypatch.setattr(monitor, "sweep_once", flaky_sweep)
    fast = dataclasses.replace(settings, sweep_interval_s=1)

    async def run_briefly():
        task = asyncio.create_task(monitor.run_monitor(fast, datetime.now(timezone.utc)))
        await asyncio.sleep(2.5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run_briefly())

    assert len(calls) >= 2
    assert "Monitor sweep failed" in caplog.text


def test_expected_agents_appear_at_startup(settings):
    with TestClient(create_app(dataclasses.replace(settings, expected_agents=("agent-db-01",)))) as client:
        agents = client.get("/agents").json()

    assert agents == [{"agent_id": "agent-db-01", "status": "pending", "first_seen": None, "last_seen": None}]
