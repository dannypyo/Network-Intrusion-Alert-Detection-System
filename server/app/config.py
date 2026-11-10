"""Server settings, read once from environment variables at startup."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = "data/monitor.db"
    host: str = "127.0.0.1"
    port: int = 8000
    offline_threshold_s: int = 30
    sweep_interval_s: int = 5
    alert_expiry_s: int = 60


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


def load_settings() -> Settings:
    return Settings(
        db_path=os.environ.get("DB_PATH", "").strip() or Settings.db_path,
        host=os.environ.get("HOST", "").strip() or Settings.host,
        port=_positive_int("PORT", Settings.port),
        offline_threshold_s=_positive_int("OFFLINE_THRESHOLD_S", Settings.offline_threshold_s),
        sweep_interval_s=_positive_int("SWEEP_INTERVAL_S", Settings.sweep_interval_s),
        alert_expiry_s=_positive_int("ALERT_EXPIRY_S", Settings.alert_expiry_s),
    )
