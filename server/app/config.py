"""Server settings, read once from environment variables at startup."""

import os
import re
from dataclasses import dataclass

from app.models import AGENT_ID_PATTERN

# Shared default so local testing needs no setup. Never use it on a deployed server.
DEV_AGENT_TOKEN = "dev-token-not-for-deployment"
MIN_TOKEN_LENGTH = 16


@dataclass(frozen=True)
class Settings:
    db_path: str = "data/monitor.db"
    host: str = "127.0.0.1"
    port: int = 8000
    offline_threshold_s: int = 30
    sweep_interval_s: int = 5
    alert_expiry_s: int = 60
    agent_token: str = DEV_AGENT_TOKEN
    expected_agents: tuple[str, ...] = ()

    @property
    def using_dev_token(self) -> bool:
        return self.agent_token == DEV_AGENT_TOKEN


def _positive_int(name: str, default: int) -> int:
    """Read a positive integer env var, or fail with a message naming it."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0, got {value}")
    return value


def _agent_token() -> str:
    """Read AGENT_TOKEN, falling back to the development token when it is not set."""
    token = os.environ.get("AGENT_TOKEN", "").strip()
    if not token:
        return DEV_AGENT_TOKEN
    if len(token) < MIN_TOKEN_LENGTH:
        raise ValueError(f"AGENT_TOKEN must be at least {MIN_TOKEN_LENGTH} characters")
    return token


def _expected_agents() -> tuple[str, ...]:
    """Read EXPECTED_AGENTS, a comma-separated list of agent IDs. Duplicates are ignored."""
    agent_ids: list[str] = []
    for part in os.environ.get("EXPECTED_AGENTS", "").split(","):
        agent_id = part.strip()
        if not agent_id:
            continue
        if not re.fullmatch(AGENT_ID_PATTERN, agent_id):
            raise ValueError(f"EXPECTED_AGENTS contains an invalid agent ID: {agent_id!r}")
        if agent_id not in agent_ids:
            agent_ids.append(agent_id)
    return tuple(agent_ids)


def load_settings() -> Settings:
    return Settings(
        db_path=os.environ.get("DB_PATH", "").strip() or Settings.db_path,
        host=os.environ.get("HOST", "").strip() or Settings.host,
        port=_positive_int("PORT", Settings.port),
        offline_threshold_s=_positive_int("OFFLINE_THRESHOLD_S", Settings.offline_threshold_s),
        sweep_interval_s=_positive_int("SWEEP_INTERVAL_S", Settings.sweep_interval_s),
        alert_expiry_s=_positive_int("ALERT_EXPIRY_S", Settings.alert_expiry_s),
        agent_token=_agent_token(),
        expected_agents=_expected_agents(),
    )
