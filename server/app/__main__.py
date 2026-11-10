"""Run the server with `python -m app`, using HOST and PORT from the environment."""

import uvicorn

from app.config import load_settings

if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)
