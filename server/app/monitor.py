"""Background monitor: marks silent agents offline and resolves stale alerts."""

import asyncio
import logging
from datetime import datetime, timezone

from app.config import Settings
from app.db import connect, prepare_agents, sweep

logger = logging.getLogger("uvicorn.error")


def prepare(settings: Settings) -> None:
    """Startup step: reset agent statuses and add the expected agents."""
    conn = connect(settings.db_path)
    try:
        prepare_agents(conn, settings.expected_agents)
    finally:
        conn.close()


def sweep_once(settings: Settings, started_at: datetime) -> None:
    """One pass of the monitor. Blocking, so it runs in a worker thread."""
    conn = connect(settings.db_path)
    try:
        went_offline, expired = sweep(
            conn, datetime.now(timezone.utc), started_at,
            settings.offline_threshold_s, settings.alert_expiry_s,
        )
    finally:
        conn.close()

    for agent_id in went_offline:
        logger.warning("%s is offline", agent_id)
    if expired:
        logger.info("Resolved %d expired alert%s", expired, "" if expired == 1 else "s")


async def run_monitor(settings: Settings, started_at: datetime) -> None:
    """Sweep every SWEEP_INTERVAL_S until the server shuts down."""
    while True:
        await asyncio.sleep(settings.sweep_interval_s)
        try:
            # to_thread keeps the blocking database work off the event loop
            await asyncio.to_thread(sweep_once, settings, started_at)
        except Exception:
            # Log and keep going, so one bad sweep cannot stop monitoring for good
            logger.exception("Monitor sweep failed; trying again next interval")
