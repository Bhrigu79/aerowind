"""
AEROWIND FastAPI Application
==============================
Main entrypoint. Wires together:
- Core configuration
- Structured logging
- Model Gateway (lifecycle)
- API routers (v1)
- Exception handlers
- CORS middleware
- Health checks
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.v1 import experiments, hypotheses, projects, providers, ai, evidence, research
from app.core.config import settings
from app.core.exceptions import (
    AerowindError,
    ExperimentNotFoundError,
    GatewayError,
    NoProvidersAvailableError,
    ProjectNotFoundError,
)
from app.core.logging import configure_logging, get_logger
from app.db.database import engine
from app.db.models import Base
from app.gateway.gateway import get_gateway

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application lifespan handler.
    Initializes and shuts down the Model Gateway cleanly.
    """
    configure_logging()
    logger.info(
        "aerowind.starting",
        env=settings.APP_ENV,
        debug=settings.APP_DEBUG,
        enabled_providers=settings.enabled_providers,
    )

    gateway = get_gateway()
    await gateway.initialize()

    # Initialize Database
    # NOTE: Base.metadata.create_all is currently kept to ensure seamless local development.
    # In a true production environment, Alembic migrations should be the sole source
    # of schema evolution, and create_all() should be removed or conditionally skipped.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("aerowind.ready", host=settings.APP_HOST, port=settings.APP_PORT)

    yield  # Application is running

    logger.info("aerowind.shutting_down")
    await gateway.shutdown()
    logger.info("aerowind.shutdown_complete")


# ── Application factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="AEROWIND",
        description=(
            "Autonomous AI Performance Engineer — "
            "Experiments on AI systems using measured evidence."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────────────────

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_timing_middleware(request: Request, call_next: object) -> Response:
        start = time.monotonic()
        response: Response = await call_next(request)  # type: ignore[operator]
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Response-Time-Ms"] = str(duration_ms)
        logger.debug(
            "http.request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    # ── Exception handlers ────────────────────────────────────────────────────

    @app.exception_handler(ProjectNotFoundError)
    async def project_not_found_handler(
        request: Request, exc: ProjectNotFoundError
    ) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=404,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(ExperimentNotFoundError)
    async def experiment_not_found_handler(
        request: Request, exc: ExperimentNotFoundError
    ) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=404,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(NoProvidersAvailableError)
    async def no_providers_handler(
        request: Request, exc: NoProvidersAvailableError
    ) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=503,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(GatewayError)
    async def gateway_error_handler(
        request: Request, exc: GatewayError
    ) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=502,
            content={"error": exc.code, "message": exc.message},
        )

    @app.exception_handler(AerowindError)
    async def aerowind_error_handler(
        request: Request, exc: AerowindError
    ) -> ORJSONResponse:
        return ORJSONResponse(
            status_code=400,
            content={"error": exc.code, "message": exc.message},
        )

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/health", tags=["System"])
    async def health() -> dict:
        gateway = get_gateway()
        status = await gateway.get_status()
        healthy_count = sum(1 for p in status.providers if p.is_healthy)
        return {
            "status": "healthy" if healthy_count > 0 else "degraded",
            "version": "0.1.0",
            "env": settings.APP_ENV,
            "providers_healthy": healthy_count,
            "providers_total": len(status.providers),
        }

    @app.get("/", tags=["System"])
    async def root() -> dict:
        return {
            "name": "AEROWIND",
            "description": "Autonomous AI Performance Engineer",
            "version": "0.1.0",
            "docs": "/docs",
        }

    # ── Routers ───────────────────────────────────────────────────────────────

    API_PREFIX = "/api/v1"
    app.include_router(projects.router, prefix=API_PREFIX)
    app.include_router(experiments.router, prefix=API_PREFIX)
    app.include_router(hypotheses.router, prefix=API_PREFIX)
    app.include_router(providers.router, prefix=API_PREFIX)
    app.include_router(ai.router, prefix=API_PREFIX)
    app.include_router(evidence.router, prefix=API_PREFIX)
    app.include_router(research.router, prefix=API_PREFIX)

    return app


app = create_app()
