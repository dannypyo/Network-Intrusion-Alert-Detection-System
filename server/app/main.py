"""FastAPI application setup: settings, startup, middleware and routes."""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings, load_settings
from app.db import init_db
from app.detection import DetectionEngine
from app.routes import router

MAX_BODY_BYTES = 1_000_000

logger = logging.getLogger("uvicorn.error")  # shows up in uvicorn's normal log output


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Tests pass their own Settings; normal runs read the environment."""
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Runs once when the server starts, before any request is handled.
        init_db(settings.db_path)
        if settings.using_dev_token:
            logger.warning("Using the development AGENT_TOKEN; set AGENT_TOKEN before deploying")
        yield

    app = FastAPI(title="Network Intrusion Detection Server", lifespan=lifespan)
    app.state.settings = settings
    # One engine for the whole server, so its history spans every report.
    # Requests run in parallel threads, so every call goes through the lock.
    app.state.detection_engine = DetectionEngine()
    app.state.detection_lock = threading.Lock()

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        """Refuse oversized bodies before FastAPI reads them into memory."""
        length = request.headers.get("content-length", "0")
        if not length.isdigit():
            return JSONResponse({"detail": "invalid Content-Length"}, status_code=400)
        if int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "request body too large"}, status_code=413)
        return await call_next(request)

    app.include_router(router)
    return app


app = create_app()
