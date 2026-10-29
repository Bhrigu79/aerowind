"""
AEROWIND — OpenAI Provider Adapter
====================================
Uses raw httpx — NO openai SDK dependency.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

import httpx

from app.core.config import settings
from app.core.exceptions import (
    GatewayError,
    GatewayTimeoutError,
    ModelNotFoundError,
    ProviderUnavailableError,
    QuotaExceededError,
    RateLimitError,
)
from app.core.logging import get_logger
from app.gateway.adapters.base import BaseProviderAdapter
from app.schemas.gateway import (
    GatewayRequest,
    GatewayResponse,
    Provider,
    ProviderHealth,
    TokenUsage,
)

logger = get_logger(__name__)

_OPENAI_BASE_URL = "https://api.openai.com/v1"

_OPENAI_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "default": {"input": 1.00, "output": 3.00},
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    key = next((k for k in _OPENAI_PRICING if k in model), "default")
    pricing = _OPENAI_PRICING[key]
    return round(
        (prompt_tokens / 1_000_000) * pricing["input"]
        + (completion_tokens / 1_000_000) * pricing["output"],
        8,
    )


class OpenAIAdapter(BaseProviderAdapter):
    """OpenAI provider adapter using raw httpx."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def is_enabled(self) -> bool:
        return settings.OPENAI_ENABLED and bool(settings.OPENAI_API_KEY)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=_OPENAI_BASE_URL,
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=float(settings.MODEL_GATEWAY_TIMEOUT),
                    write=10.0,
                    pool=5.0,
                ),
            )
        return self._client

    def _resolve_model(self, request: GatewayRequest) -> str:
        return request.preferred_model or settings.OPENAI_DEFAULT_MODEL

    def _build_payload(self, request: GatewayRequest, model: str) -> dict[str, Any]:
        return {
            "model": model,
            "messages": [
                {"role": msg.role.value, "content": msg.content}
                for msg in request.messages
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
        }

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        model = self._resolve_model(request)
        payload = self._build_payload(request, model)
        client = self._get_client()
        start_ms = self._now_ms()
        request_id = str(uuid.uuid4())

        try:
            response = await client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(
                provider="openai", timeout=settings.MODEL_GATEWAY_TIMEOUT
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(provider="openai") from exc

        latency_ms = self._now_ms() - start_ms
        await self._handle_error_response(response)

        data = response.json()
        choice = data["choices"][0]
        usage_data = data.get("usage", {})
        prompt_tokens = usage_data.get("prompt_tokens", 0)
        completion_tokens = usage_data.get("completion_tokens", 0)

        return GatewayResponse(
            content=choice["message"]["content"] or "",
            provider=Provider.OPENAI,
            model=model,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=usage_data.get("total_tokens", prompt_tokens + completion_tokens),
            ),
            latency_ms=round(latency_ms, 2),
            request_id=request_id,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def stream(self, request: GatewayRequest) -> AsyncIterator[str]:
        model = self._resolve_model(request)
        payload = self._build_payload(request, model)
        payload["stream"] = True
        client = self._get_client()

        try:
            async with client.stream("POST", "/chat/completions", json=payload) as response:
                await self._handle_error_response(response)
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            break
                        try:
                            data = json.loads(chunk)
                            delta = data["choices"][0].get("delta", {})
                            if content := delta.get("content"):
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(
                provider="openai", timeout=settings.MODEL_GATEWAY_TIMEOUT
            ) from exc

    async def health_check(self) -> ProviderHealth:
        import datetime

        if not self.is_enabled:
            return ProviderHealth(
                provider=Provider.OPENAI,
                is_healthy=False,
                last_checked_at=datetime.datetime.utcnow().isoformat(),
                message="Provider disabled or API key not set",
            )

        from app.schemas.gateway import GatewayRequest, Message, MessageRole, TaskType

        probe = GatewayRequest(
            task_type=TaskType.GENERAL,
            messages=[Message(role=MessageRole.USER, content="ping")],
            max_tokens=5,
            temperature=0.0,
        )
        start_ms = self._now_ms()
        try:
            await self.complete(probe)
            return ProviderHealth(
                provider=Provider.OPENAI,
                is_healthy=True,
                last_checked_at=datetime.datetime.utcnow().isoformat(),
                avg_latency_ms=round(self._now_ms() - start_ms, 2),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(
                provider=Provider.OPENAI,
                is_healthy=False,
                last_checked_at=datetime.datetime.utcnow().isoformat(),
                message=str(exc)[:200],
            )

    @staticmethod
    async def _handle_error_response(response: httpx.Response) -> None:
        if response.status_code == 200:
            return
        body = ""
        try:
            body = response.text
        except Exception:  # noqa: BLE001
            pass

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise RateLimitError(
                provider="openai",
                retry_after=float(retry_after) if retry_after else None,
            )
        if response.status_code == 402:
            raise QuotaExceededError(provider="openai")
        if response.status_code == 404:
            raise ModelNotFoundError(model="unknown", provider="openai")
        if response.status_code in (502, 503, 504):
            raise ProviderUnavailableError(provider="openai")

        raise GatewayError(
            f"OpenAI API error {response.status_code}: {body[:300]}",
            code="OPENAI_API_ERROR",
        )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
