"""HTTP endpoints and the dependencies they share."""

import hmac
import logging
import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError

from app.db import connect, save_alerts, store_report, utc_now
from app.models import AlertSignal, Report

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


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
