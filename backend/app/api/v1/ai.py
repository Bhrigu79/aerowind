"""
AEROWIND API v1 — AI Testing Endpoint
======================================
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.gateway.gateway import ModelGateway, get_gateway
from app.schemas.gateway import (
    GatewayRequest,
    Message,
    MessageRole,
    Provider,
    TaskType,
)

router = APIRouter(prefix="/ai", tags=["AI Integration"])
logger = get_logger(__name__)


class AITestRequest(BaseModel):
    prompt: str = Field(..., description="The prompt to test")
    provider: Provider | None = Field(None, description="Optional provider override")
    model: str | None = Field(None, description="Optional model override")


class AITestResponse(BaseModel):
    provider: str
    model: str
    text: str
    latency_ms: float
    usage: dict[str, int]
    request_id: str
    was_fallback: bool


def _get_gw() -> ModelGateway:
    return get_gateway()


@router.post("/test", response_model=AITestResponse)
async def test_ai_call(
    body: AITestRequest,
    gateway: ModelGateway = Depends(_get_gw),
) -> AITestResponse:
    """Test the AI gateway with a simple prompt."""

    req = GatewayRequest(
        task_type=TaskType.GENERAL,
        messages=[
            Message(role=MessageRole.USER, content=body.prompt)
        ],
        preferred_provider=body.provider,
        preferred_model=body.model,
    )

    try:
        response = await gateway.complete(req)

        return AITestResponse(
            provider=response.provider.value,
            model=response.model,
            text=response.content,
            latency_ms=response.latency_ms,
            usage=response.usage.model_dump(),
            request_id=response.request_id,
            was_fallback=response.was_fallback,
        )
    except Exception as exc:
        logger.error("ai.test_failed", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail="External model provider request failed."
        ) from exc
