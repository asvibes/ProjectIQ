"""FastAPI application entry point.

Run locally (from ``backend/``)::

    uvicorn app.main:app --reload
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.routers import discover_routers

APP_TITLE = "ProjectIQ API"
APP_DESCRIPTION = (
    "Local-first project intelligence: document understanding, requirement matching, "
    "deterministic costing and decision briefings. Decision support only."
)

# Vite (5173), Create React App / Next (3000), on both hostnames a browser may use.
DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def register_routers(app: FastAPI) -> list[str]:
    """Mount every discovered router and return the module names that were mounted."""
    names: list[str] = []
    for name, router in discover_routers():
        app.include_router(router)
        names.append(name)
    return names


def create_app(
    *,
    cors_origins: Optional[Sequence[str]] = None,
    init_database: bool = True,
) -> FastAPI:
    """Application factory.

    ``init_database=False`` skips table creation at startup (used by tests so they never
    touch the real SQLite file).
    """
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if init_database:
            # Imported lazily: app.database builds the engine at import time.
            from app.database import init_db

            init_db()
        yield

    app = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins if cors_origins is not None else DEFAULT_CORS_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"], summary="Liveness check")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": APP_TITLE,
            "version": __version__,
            "environment": settings.app_env,
        }

    app.state.registered_routers = register_routers(app)
    return app


app = create_app()