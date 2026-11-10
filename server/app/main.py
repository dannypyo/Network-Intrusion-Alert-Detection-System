"""FastAPI application factory and routes."""

from fastapi import FastAPI

from app.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app. Tests pass their own Settings; normal runs read the environment."""
    settings = settings or load_settings()

    app = FastAPI(title="Network Intrusion Detection Server")
    app.state.settings = settings

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    return app


app = create_app()
