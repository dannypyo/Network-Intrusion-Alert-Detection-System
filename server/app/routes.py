"""HTTP endpoints and the dependencies they share."""

import hmac
import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.db import connect, store_report, utc_now
from app.models import Report

router = APIRouter()


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


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.post("/report", dependencies=[Depends(require_token)])
def post_report(
    report: Report,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    report_id = store_report(conn, report, utc_now())
    return {"status": "ok", "report_id": report_id}
