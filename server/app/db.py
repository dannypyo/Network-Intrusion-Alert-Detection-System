"""SQLite connection setup, schema creation, and timestamp helpers.

All of the server's SQL lives in this module.
"""

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models import AlertSignal, Report

SCHEMA_VERSION = 2
OFFLINE_ALERT_TYPE = "AGENT_OFFLINE"
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
CREATE INDEX IF NOT EXISTS idx_reports_time ON reports (received_at);

CREATE TABLE IF NOT EXISTS failed_logins (
    id        INTEGER PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES reports (id) ON DELETE CASCADE,
    user      TEXT NOT NULL,
    source_ip TEXT NOT NULL,
    time      TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_failed_logins_ip_time ON failed_logins (source_ip, time);
CREATE INDEX IF NOT EXISTS idx_failed_logins_report ON failed_logins (report_id);

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
    type        TEXT NOT NULL,
    severity    TEXT NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH')),
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


def store_report(conn: sqlite3.Connection, report: Report, received_at: str) -> tuple[int, bool]:
    """Store one validated report in a single transaction.

    Registers the agent on its first report and marks it online with last_seen = received_at.
    If the agent had an active offline alert, resolves it.

    Returns the new report id, and whether the agent just came back online.
    """
    with conn:  # commits if everything succeeds, rolls back if anything raises
        came_back = conn.execute(
            "UPDATE alerts SET status = 'resolved', resolved_at = ? WHERE key = ? AND status = 'active'",
            (received_at, f"{OFFLINE_ALERT_TYPE}:{report.agent_id}"),
        ).rowcount > 0
        conn.execute(
            """
            INSERT INTO agents (agent_id, status, first_seen, last_seen)
            VALUES (?, 'online', ?, ?)
            ON CONFLICT (agent_id) DO UPDATE SET
                status = 'online',
                first_seen = COALESCE(agents.first_seen, excluded.first_seen),
                last_seen = excluded.last_seen
            """,
            (report.agent_id, received_at, received_at),
        )
        t = report.traffic
        report_id = conn.execute(
            """
            INSERT INTO reports (agent_id, agent_ts, received_at, bytes_in, bytes_out,
                                 packets_in, packets_out, interval_s)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (report.agent_id, to_db_time(report.timestamp), received_at,
             t.bytes_in, t.bytes_out, t.packets_in, t.packets_out, t.interval_s),
        ).lastrowid
        conn.executemany(
            "INSERT INTO failed_logins (report_id, user, source_ip, time) VALUES (?, ?, ?, ?)",
            [(report_id, f.user, str(f.source_ip), to_db_time(f.time)) for f in report.failed_logins],
        )
        conn.executemany(
            """
            INSERT INTO service_checks (report_id, name, host, port, up, response_ms, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [(report_id, s.name, s.host, s.port, int(s.up), s.response_ms, s.error)
             for s in report.services],
        )
    return report_id, came_back


def save_alerts(conn: sqlite3.Connection, alerts: list[AlertSignal], now: str) -> None:
    """Insert each alert, or update the active alert that already has its key.

    The partial unique index on (key) WHERE status = 'active' makes this one statement
    safe even when two requests save the same key at the same moment.
    """
    with conn:
        _upsert_alerts(conn, alerts, now)


def _upsert_alerts(conn: sqlite3.Connection, alerts: list[AlertSignal], now: str) -> None:
    """The insert-or-update behind save_alerts, for use inside an open transaction."""
    conn.executemany(
        """
        INSERT INTO alerts (key, type, severity, agent_id, message, status, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
        ON CONFLICT (key) WHERE status = 'active' DO UPDATE SET
            message = excluded.message,
            last_seen = excluded.last_seen,
            count = count + 1
        """,
        [(a.key, a.type, a.severity, a.agent_id, a.message, now, now) for a in alerts],
    )


def prepare_agents(conn: sqlite3.Connection, expected_agents: tuple[str, ...]) -> None:
    """Run once at startup.

    Agents that were online are set to pending: the server was down, so their status is
    unknown until they report again. Offline agents stay offline. Expected agents the
    server has never seen are added as pending.
    """
    with conn:
        conn.execute("UPDATE agents SET status = 'pending' WHERE status = 'online'")
        conn.executemany(
            "INSERT INTO agents (agent_id, status) VALUES (?, 'pending') ON CONFLICT (agent_id) DO NOTHING",
            [(agent_id,) for agent_id in expected_agents],
        )


def sweep(
    conn: sqlite3.Connection,
    now: datetime,
    started_at: datetime,
    offline_after_s: int,
    expire_after_s: int,
) -> tuple[list[str], int]:
    """Mark silent agents offline and resolve stale alerts, in one transaction.

    Silence is measured from the later of an agent's last report and the server start,
    which gives every agent a grace period after a restart.

    Returns the agents that just went offline and the number of alerts resolved.
    """
    now_text = to_db_time(now)
    silent_since = to_db_time(now - timedelta(seconds=offline_after_s))
    expired_before = to_db_time(now - timedelta(seconds=expire_after_s))

    with conn:
        # One statement finds and updates the agents, so a report arriving at the
        # same moment cannot be overwritten. Agents already offline are skipped.
        went_offline = conn.execute(
            """
            UPDATE agents SET status = 'offline'
            WHERE status != 'offline' AND MAX(COALESCE(last_seen, ''), ?) < ?
            RETURNING agent_id, last_seen
            """,
            (to_db_time(started_at), silent_since),
        ).fetchall()

        _upsert_alerts(conn, [
            AlertSignal(
                key=f"{OFFLINE_ALERT_TYPE}:{row['agent_id']}",
                type=OFFLINE_ALERT_TYPE,
                severity="HIGH",
                agent_id=row["agent_id"],
                message=(
                    f"{row['agent_id']} has not reported for over {offline_after_s}s "
                    f"(last report {row['last_seen']})"
                    if row["last_seen"]
                    else f"{row['agent_id']} has not reported since the server started"
                ),
            )
            for row in went_offline
        ], now_text)

        # Offline alerts never expire: nothing re-signals them while the agent is silent.
        # They are resolved in store_report when the agent reports again.
        expired = conn.execute(
            """
            UPDATE alerts SET status = 'resolved', resolved_at = ?
            WHERE status = 'active' AND type != ? AND last_seen < ?
            """,
            (now_text, OFFLINE_ALERT_TYPE, expired_before),
        ).rowcount

    return [row["agent_id"] for row in went_offline], expired


def list_agents(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT agent_id, status, first_seen, last_seen FROM agents ORDER BY agent_id")
    return [dict(row) for row in rows]


def list_alerts(conn: sqlite3.Connection, status: str, limit: int) -> list[dict]:
    """Alerts with the given status ('active', 'resolved' or 'all'), most recently signaled first."""
    rows = conn.execute(
        """
        SELECT id, key, type, severity, agent_id, message, status,
               first_seen, last_seen, count, resolved_at
        FROM alerts
        WHERE ? = 'all' OR status = ?
        ORDER BY last_seen DESC, id DESC
        LIMIT ?
        """,
        (status, status, limit),
    )
    return [dict(row) for row in rows]


def list_metrics(conn: sqlite3.Connection, agent_id: str | None, since: str, limit: int) -> list[dict]:
    """Reports received since `since`, oldest first, each with its service checks.

    When more than `limit` reports match, the newest `limit` are kept.
    """
    reports = conn.execute(
        """
        SELECT * FROM (
            SELECT id, agent_id, received_at, bytes_in, bytes_out, packets_in, packets_out, interval_s
            FROM reports
            WHERE received_at >= ? AND (? IS NULL OR agent_id = ?)
            ORDER BY received_at DESC, id DESC
            LIMIT ?
        )
        ORDER BY received_at, id
        """,
        (since, agent_id, agent_id, limit),
    ).fetchall()
    if not reports:
        return []

    # One query each for the services and login counts of all chosen reports.
    # Only "?" placeholders are built here; the ids themselves are passed as parameters.
    ids = [row["id"] for row in reports]
    placeholders = ",".join("?" * len(ids))
    services = defaultdict(list)
    for row in conn.execute(
        f"SELECT report_id, name, up, response_ms, error FROM service_checks "
        f"WHERE report_id IN ({placeholders}) ORDER BY id",
        ids,
    ):
        services[row["report_id"]].append(
            {"name": row["name"], "up": bool(row["up"]), "response_ms": row["response_ms"], "error": row["error"]}
        )
    login_counts = dict(conn.execute(
        f"SELECT report_id, count(*) FROM failed_logins WHERE report_id IN ({placeholders}) GROUP BY report_id",
        ids,
    ).fetchall())

    return [
        {
            "report_id": r["id"],
            "agent_id": r["agent_id"],
            "received_at": r["received_at"],
            "traffic": {key: r[key] for key in ("bytes_in", "bytes_out", "packets_in", "packets_out", "interval_s")},
            "failed_logins": login_counts.get(r["id"], 0),
            "services": services[r["id"]],
        }
        for r in reports
    ]
