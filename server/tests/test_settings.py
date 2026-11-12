"""Server settings read from environment variables."""

import pytest

from app.config import DEV_AGENT_TOKEN, load_settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in ("AGENT_TOKEN", "EXPECTED_AGENTS", "PORT", "SWEEP_INTERVAL_S", "DB_PATH"):
        monkeypatch.delenv(name, raising=False)


def test_defaults():
    settings = load_settings()
    assert settings.agent_token == DEV_AGENT_TOKEN and settings.using_dev_token
    assert settings.expected_agents == ()
    assert settings.port == 8000


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_token_falls_back_to_dev_token(monkeypatch, value):
    monkeypatch.setenv("AGENT_TOKEN", value)
    assert load_settings().using_dev_token


def test_short_token_rejected(monkeypatch):
    monkeypatch.setenv("AGENT_TOKEN", "changeme")
    with pytest.raises(ValueError, match="AGENT_TOKEN"):
        load_settings()


def test_custom_token_accepted(monkeypatch):
    monkeypatch.setenv("AGENT_TOKEN", "x" * 32)
    settings = load_settings()
    assert settings.agent_token == "x" * 32 and not settings.using_dev_token


def test_expected_agents_parsed(monkeypatch):
    monkeypatch.setenv("EXPECTED_AGENTS", " agent-web-01, agent-db-01,agent-web-01,, ")
    assert load_settings().expected_agents == ("agent-web-01", "agent-db-01")


def test_invalid_expected_agent_rejected(monkeypatch):
    monkeypatch.setenv("EXPECTED_AGENTS", "agent-web-01,bad id")
    with pytest.raises(ValueError, match="bad id"):
        load_settings()


@pytest.mark.parametrize("name, value", [("PORT", "abc"), ("PORT", "0"), ("SWEEP_INTERVAL_S", "-5"), ("SWEEP_INTERVAL_S", "2.5")])
def test_bad_numbers_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        load_settings()
