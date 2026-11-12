"""GET /timeline: the demo runner's progress, read from its status file."""

import json
from pathlib import Path

import pytest

from app.config import load_settings

EMPTY = {"active": False, "started_at": None, "finished_at": None, "settings": {}, "steps": [], "unexpected_alerts": []}

TIMELINE = {
    "active": True,
    "started_at": "2026-11-11T20:00:00.000000Z",
    "finished_at": None,
    "settings": {"report_interval_s": 5, "offline_threshold_s": 15},
    "steps": [
        {"name": "Brute-force login", "description": "8 wrong passwords from 10.0.0.66", "expect": "BRUTE_FORCE_LOGIN",
         "state": "detected", "started_at": "2026-11-11T20:00:05.000000Z", "detected_in_s": 7.9, "detail": None},
        {"name": "Traffic spike", "description": "Parallel large downloads", "expect": "TRAFFIC_SPIKE",
         "state": "pending", "started_at": None, "detected_in_s": None, "detail": None},
    ],
    "unexpected_alerts": [],
}


def write_timeline(settings, data):
    """Write the timeline file the server reads. A string is written as-is."""
    text = data if isinstance(data, str) else json.dumps(data)
    Path(settings.timeline_path).write_text(text, encoding="utf-8")


def step(state):
    return {"name": "Step", "description": "d", "state": state}


def test_no_file_gives_an_empty_timeline(client, caplog):
    response = client.get("/timeline")

    assert response.status_code == 200
    assert response.json() == EMPTY
    assert "timeline" not in caplog.text


def test_timeline_file_is_returned(client, settings):
    write_timeline(settings, {**TIMELINE, "extra_field": "dropped"})

    assert client.get("/timeline").json() == TIMELINE


@pytest.mark.parametrize("state", ["pending", "running", "detected", "missed", "done"])
def test_every_state_is_accepted(client, settings, state):
    write_timeline(settings, {"active": True, "steps": [step(state)]})

    assert client.get("/timeline").json()["steps"][0]["state"] == state


@pytest.mark.parametrize("contents", [
    '{"active": true, "steps": [{"name": "x", "descr',          # cut off while being written
    json.dumps({"active": True, "steps": [step("exploded")]}),  # a state that does not exist
], ids=["half-written", "unknown state"])
def test_unreadable_file_gives_an_empty_timeline(client, settings, caplog, contents):
    write_timeline(settings, contents)

    assert client.get("/timeline").json() == EMPTY
    assert "Ignoring unreadable timeline file" in caplog.text


def test_timeline_needs_no_token(client):
    assert client.get("/timeline").status_code == 200


def test_timeline_is_in_the_api_docs(client):
    assert "/timeline" in client.get("/openapi.json").json()["paths"]


def test_timeline_path_setting(monkeypatch):
    monkeypatch.delenv("TIMELINE_PATH", raising=False)
    assert load_settings().timeline_path.endswith(str(Path("demo_logs") / "timeline.json"))

    monkeypatch.setenv("TIMELINE_PATH", "/tmp/elsewhere.json")
    assert load_settings().timeline_path == "/tmp/elsewhere.json"
