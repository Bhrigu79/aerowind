"""
AEROWIND — Anthropic Provider Adapter
=======================================
Uses Anthropic's Messages API via raw httpx.
Maps Anthropic's request/response format to the provider-agnostic schema.
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
    Message,
    MessageRole,
    Provider,
    ProviderHealth,
    TokenUsage,
)

logger = get_logger(__name__)

_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
_ANTHROPIC_VERSION = "2023-06-01"

_ANTHROPIC_PRICING: dict[str, dict[str, float]] = {
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku": {"input": 0.80, "output": 4.00},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "default": {"input": 3.00, "output": 15.00},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    key = next((k for k in _ANTHROPIC_PRICING if k in model), "default")
    pricing = _ANTHROPIC_PRICING[key]
    return round(
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"],
        8,
    )


def _split_messages(messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
    """
    Anthropic separates the system prompt from the messages list.
    Extract the system message (if any) and format the rest.
    """
    system_prompt: str | None = None
    chat_messages: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == MessageRole.SYSTEM:
            system_prompt = msg.content
        else:
            chat_messages.append({"role": msg.role.value, "content": msg.content})

    return system_prompt, chat_messages


class AnthropicAdapter(BaseProviderAdapter):
    """Anthropic Claude adapter via raw httpx."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def is_enabled(self) -> bool:
        return settings.ANTHROPIC_ENABLED and bool(settings.ANTHROPIC_API_KEY)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=_ANTHROPIC_BASE_URL,
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": _ANTHROPIC_VERSION,
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
        return request.preferred_model or settings.ANTHROPIC_DEFAULT_MODEL

    def _build_payload(
        self,
        request: GatewayRequest,
        model: str,
        stream: bool = False,
    ) -> dict[str, Any]:
        system_prompt, chat_messages = _split_messages(request.messages)
        payload: dict[str, Any] = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": stream,
        }
        if system_prompt:
            payload["system"] = system_prompt
        return payload

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        model = self._resolve_model(request)
        payload = self._build_payload(request, model)
        client = self._get_client()
        start_ms = self._now_ms()
        request_id = str(uuid.uuid4())

        try:
            response = await client.post("/v1/messages", json=payload)
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(
                provider="anthropic", timeout=settings.MODEL_GATEWAY_TIMEOUT
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(provider="anthropic") from exc

        latency_ms = self._now_ms() - start_ms
        await self._handle_error_response(response)

        data = response.json()
        # Anthropic returns content as a list of blocks
        content_blocks = data.get("content", [])
        text = " ".join(
            block["text"] for block in content_blocks if block.get("type") == "text"
        )

        usage_data = data.get("usage", {})
        input_tokens = usage_data.get("input_tokens", 0)
        output_tokens = usage_data.get("output_tokens", 0)

        return GatewayResponse(
            content=text,
            provider=Provider.ANTHROPIC,
            model=model,
            usage=TokenUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            latency_ms=round(latency_ms, 2),
            request_id=request_id,
            finish_reason=data.get("stop_reason", "stop"),
        )

    async def stream(self, request: GatewayRequest) -> AsyncIterator[str]:
        model = self._resolve_model(request)
        payload = self._build_payload(request, model, stream=True)
        client = self._get_client()

        try:
            async with client.stream("POST", "/v1/messages", json=payload) as response:
                await self._handle_error_response(response)
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        chunk = line[6:]
                        try:
                            data = json.loads(chunk)
                            event_type = data.get("type", "")
                            if event_type == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                            elif event_type == "message_stop":
                                break
                        except (json.JSONDecodeError, KeyError):
                            continue
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(
                provider="anthropic", timeout=settings.MODEL_GATEWAY_TIMEOUT
            ) from exc

    async def health_check(self) -> ProviderHealth:
        import datetime

        if not self.is_enabled:
            return ProviderHealth(
                provider=Provider.ANTHROPIC,
                is_healthy=False,
                last_checked_at=datetime.datetime.utcnow().isoformat(),
                message="Provider disabled or API key not set",
            )

        from app.schemas.gateway import GatewayRequest, TaskType

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
                provider=Provider.ANTHROPIC,
                is_healthy=True,
                last_checked_at=datetime.datetime.utcnow().isoformat(),
                avg_latency_ms=round(self._now_ms() - start_ms, 2),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(
                provider=Provider.ANTHROPIC,
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
                provider="anthropic",
                retry_after=float(retry_after) if retry_after else None,
            )
        if response.status_code == 402:
            raise QuotaExceededError(provider="anthropic")
        if response.status_code == 404:
            raise ModelNotFoundError(model="unknown", provider="anthropic")
        if response.status_code in (502, 503, 504):
            raise ProviderUnavailableError(provider="anthropic")

        raise GatewayError(
            f"Anthropic API error {response.status_code}: {body[:300]}",
            code="ANTHROPIC_API_ERROR",
        )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
