"""
AEROWIND API v1 — Provider / Gateway Router
=============================================
Exposes Model Gateway status, provider health, and a direct completion
endpoint for testing provider connectivity.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.logging import get_logger
from app.gateway.gateway import ModelGateway, get_gateway
from app.schemas.gateway import (
    GatewayRequest,
    GatewayResponse,
    GatewayStatus,
)

router = APIRouter(prefix="/gateway", tags=["Model Gateway"])
logger = get_logger(__name__)


def _get_gw() -> ModelGateway:
    return get_gateway()


@router.get("/status", response_model=GatewayStatus)
async def get_gateway_status(gateway: ModelGateway = Depends(_get_gw)) -> GatewayStatus:
    """
    Return full gateway status including:
    - Provider health
    - Global usage statistics
    - Cost estimates
    """
    return await gateway.get_status()


@router.post("/complete", response_model=GatewayResponse)
async def gateway_complete(
    request: GatewayRequest,
    gateway: ModelGateway = Depends(_get_gw),
) -> GatewayResponse:
    """
    Direct completion endpoint — primarily for testing provider connectivity.

    In production, agents call the gateway programmatically, not via HTTP.
    This endpoint is useful for verifying API keys and provider health.
    """
    try:
        response = await gateway.complete(request)
        return response
    except Exception as exc:
        logger.error("gateway.api_complete_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail="External model provider request failed."
        ) from exc


@router.get("/usage")
async def get_usage_stats(gateway: ModelGateway = Depends(_get_gw)) -> dict:
    """Return global usage statistics."""
    return gateway.usage_tracker.get_global_stats()
