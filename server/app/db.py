"""SQLite connection setup, schema creation, and timestamp helpers.

All of the server's SQL lives in this module.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
MIN_SQLITE_VERSION = (3, 37, 0)  # first version with STRICT tables

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id   TEXT PRIMARY KEY,
    status     TEXT NOT NULL CHECK (status IN ('online', 'offline', 'pending')),
    first_seen TEXT,
    last_seen  TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY,
    agent_id    TEXT NOT NULL REFERENCES agents (agent_id),
    agent_ts    TEXT NOT NULL,
    received_at TEXT NOT NULL,
    bytes_in    INTEGER NOT NULL CHECK (bytes_in >= 0),
    bytes_out   INTEGER NOT NULL CHECK (bytes_out >= 0),
    packets_in  INTEGER NOT NULL CHECK (packets_in >= 0),
    packets_out INTEGER NOT NULL CHECK (packets_out >= 0),
    interval_s  REAL NOT NULL CHECK (interval_s > 0)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_reports_agent_time ON reports (agent_id, received_at);

CREATE TABLE IF NOT EXISTS failed_logins (
    id        INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES reports (id) ON DELETE CASCADE,
    user      TEXT NOT NULL,
    source_ip TEXT NOT NULL,
    time      TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_failed_logins_ip_time ON failed_logins (source_ip, time);

CREATE TABLE IF NOT EXISTS service_checks (
    id          INTEGER PRIMARY KEY,
    report_id   INTEGER NOT NULL REFERENCES reports (id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    host        TEXT NOT NULL,
    port        INTEGER NOT NULL,
    up          INTEGER NOT NULL CHECK (up IN (0, 1)),
    response_ms REAL,
    error       TEXT
) STRICT;
CREATE INDEX IF NOT EXISTS idx_service_checks_report ON service_checks (report_id);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY,
    key         TEXT NOT NULL,
    rule        TEXT NOT NULL,
    severity    TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    agent_id    TEXT REFERENCES agents (agent_id),
    message     TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('active', 'resolved')),
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    count       INTEGER NOT NULL DEFAULT 1 CHECK (count >= 1),
    resolved_at TEXT
) STRICT;
-- At most one active alert per key, so deduplication holds even under concurrent requests.
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_one_active_per_key ON alerts (key) WHERE status = 'active';
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open a connection with the settings every request needs."""
    # timeout=5.0 is SQLite's busy timeout: wait up to 5 s for another writer instead of failing.
    # check_same_thread=False: FastAPI may open the connection and run the endpoint on different
    # threads of its pool. Each connection still serves only one request at a time.
    conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # off by default, and set per connection
    conn.execute("PRAGMA synchronous = NORMAL")  # safe with WAL; only a power loss can drop the last writes
    return conn


def init_db(db_path: str) -> None:
    """Create the folder, tables and indexes. Safe to run on every startup."""
    if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
        needed = ".".join(map(str, MIN_SQLITE_VERSION))
        raise RuntimeError(f"SQLite {needed}+ is required, found {sqlite3.sqlite_version}")

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise RuntimeError(
                f"Database schema is version {version}, but this server needs version "
                f"{SCHEMA_VERSION}. Delete {db_path} and restart the server."
            )
        conn.execute("PRAGMA journal_mode = WAL")  # stored in the file, so set once here
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    finally:
        conn.close()


def to_db_time(dt: datetime) -> str:
    """Convert a timezone-aware datetime to the single stored format, e.g. 2026-11-10T01:14:56.897391Z.

    Every stored time uses this exact format so that text comparison matches time order.
    """
    if dt.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return utc.isoformat(timespec="microseconds") + "Z"


def utc_now() -> str:
    """The current server time in the stored format."""
    return to_db_time(datetime.now(timezone.utc))
