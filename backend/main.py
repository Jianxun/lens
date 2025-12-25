from __future__ import annotations

import os

import httpx
from typing import Optional

from fastapi import FastAPI

from backend.api import chat, retrieval, sessions

EMBEDDING_BASE_URL = "https://space.ai-builders.com/backend/v1"
EMBEDDING_API_KEY_ENV = "SUPER_MIND_API_KEY"


def dsn_from_env() -> str:
    user = os.environ.get("POSTGRES_USER", "lens")
    password = os.environ.get("POSTGRES_PASSWORD", "lens")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "lens")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def build_embedding_client() -> Optional[httpx.Client]:
    api_key = os.environ.get(EMBEDDING_API_KEY_ENV)
    if not api_key:
        # Embedding calls require this key; allow startup without it for local dev.
        return None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    return httpx.Client(base_url=EMBEDDING_BASE_URL, headers=headers, timeout=60.0)


def create_app() -> FastAPI:
    app = FastAPI(title="Lens API")

    app.state.dsn = dsn_from_env()
    app.state.embedding_client = build_embedding_client()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        client = getattr(app.state, "embedding_client", None)
        if client:
            client.close()

    app.include_router(retrieval.router)
    app.include_router(sessions.router)
    app.include_router(chat.router)
    return app


app = create_app()

