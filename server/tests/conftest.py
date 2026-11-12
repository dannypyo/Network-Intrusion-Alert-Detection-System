"""Shared fixtures: a fresh app and database for every test."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

TEST_TOKEN = "test-token-0123456789"


@pytest.fixture
def settings(tmp_path):
    # Each test gets its own database file. A one-hour sweep interval keeps the
    # background monitor from running during a test; its logic is tested directly.
    return Settings(db_path=str(tmp_path / "test.db"), agent_token=TEST_TOKEN, sweep_interval_s=3600)


@pytest.fixture
def client(settings):
    # "with" runs the app's startup and shutdown, so the database is created as it is for real
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def auth():
    return {"X-Agent-Token": TEST_TOKEN}
