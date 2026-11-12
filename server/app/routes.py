"""HTTP endpoints and the dependencies they share."""

import hmac
import logging
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.db import (connect, list_agents, list_alerts, list_metrics, save_alerts,
                    store_report, to_db_time, utc_now)
from app.models import AGENT_ID_PATTERN, AgentOut, AlertOut, AlertSignal, MetricOut, Report, TimelineOut

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

# <repo root>/dashboard/index.html, found from this file's location (server/app/routes.py),
# so it works no matter which folder the server is started from
DASHBOARD_FILE = Path(__file__).resolve().parents[2] / "dashboard" / "index.html"


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """Open one connection for this request and always close it afterwards."""
    conn = connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def require_token(
    request: Request,
    x_agent_token: Annotated[str | None, Header()] = None,
) -> None:
    """Reject the request with 401 unless X-Agent-Token matches AGENT_TOKEN."""
    expected = request.app.state.settings.agent_token
    # compare_digest takes the same time wherever the strings differ, so response timing
    # reveals nothing about the token. Bytes, because it rejects non-ASCII str input.
    if x_agent_token is None or not hmac.compare_digest(x_agent_token.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing or invalid X-Agent-Token")


def run_detection(state, report: Report) -> list[AlertSignal]:
    """Run the shared detection engine on one report. Never raises.

    A crash or a malformed alert is logged and skipped, so a bug in a rule
    cannot lose the report that was already stored.
    """
    try:
        with state.detection_lock:
            raw_alerts = list(state.detection_engine.evaluate_report(report.model_dump(mode="json")))
    except Exception:
        logger.exception("Detection failed on a report from %s", report.agent_id)
        return []

    signals = []
    for raw in raw_alerts:
        try:
            signals.append(AlertSignal.model_validate(raw))
        except ValidationError as error:
            logger.error("Skipping malformed alert %r: %s", raw, error)
    return signals


@router.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    """Serve Matthew's dashboard. Only this one file is served, never the rest of the folder."""
    if not DASHBOARD_FILE.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
    return FileResponse(DASHBOARD_FILE)


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.post("/report", dependencies=[Depends(require_token)])
def post_report(
    request: Request,
    report: Report,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    received_at = utc_now()
    report_id, came_back = store_report(conn, report, received_at)  # committed on its own
    if came_back:
        logger.info("%s is back online", report.agent_id)

    signals = run_detection(request.app.state, report)
    try:
        save_alerts(conn, signals, received_at)
    except sqlite3.Error:
        # The report is already stored, so answer 200 and leave the error in the log
        logger.exception("Could not save alerts for report %s", report_id)
        signals = []

    return {"status": "ok", "report_id": report_id, "alerts": len(signals)}


@router.get("/agents", response_model=list[AgentOut])
def get_agents(conn: Annotated[sqlite3.Connection, Depends(get_db)]) -> list[dict]:
    return list_agents(conn)


@router.get("/alerts", response_model=list[AlertOut])
def get_alerts(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    status: Literal["active", "resolved", "all"] = "active",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[dict]:
    return list_alerts(conn, status, limit)


@router.get("/metrics", response_model=list[MetricOut])
def get_metrics(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    agent_id: Annotated[str | None, Query(pattern=AGENT_ID_PATTERN)] = None,
    since_seconds: Annotated[int, Query(ge=1, le=86_400)] = 300,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> list[dict]:
    since = to_db_time(datetime.now(timezone.utc) - timedelta(seconds=since_seconds))
    return list_metrics(conn, agent_id, since, limit)


@router.get("/timeline", response_model=TimelineOut)
def get_timeline(request: Request) -> TimelineOut:
    """The attack sequence run by demo.py, or an inactive timeline when none is running."""
    path = Path(request.app.state.settings.timeline_path)
    try:
        return TimelineOut.model_validate_json(path.read_bytes())
    except FileNotFoundError:
        return TimelineOut()  # the normal case whenever the demo runner is not running
    except (OSError, ValidationError) as error:
        logger.warning("Ignoring unreadable timeline file %s: %s", path, error)
        return TimelineOut()
