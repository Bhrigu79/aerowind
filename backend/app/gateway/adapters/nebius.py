"""
AEROWIND — Nebius / NVIDIA Nemotron Provider Adapter
=====================================================
Nebius AI Cloud exposes an OpenAI-compatible API endpoint.
This adapter uses raw httpx (NO openai SDK) so we control the full stack.

Primary model family: NVIDIA Nemotron (nvidia/llama-3.1-nemotron-70b-instruct)
Fast model: meta-llama/Meta-Llama-3.1-8B-Instruct
"""

from __future__ import annotations

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

# Nebius pricing (USD per 1M tokens) — update as Nebius publishes rates
_NEBIUS_PRICING: dict[str, dict[str, float]] = {
    "nvidia/llama-3.1-nemotron-70b-instruct": {
        "input": 0.13,
        "output": 0.40,
    },
    "meta-llama/Meta-Llama-3.1-8B-Instruct": {
        "input": 0.02,
        "output": 0.05,
    },
    "default": {"input": 0.20, "output": 0.50},
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = _NEBIUS_PRICING.get(model, _NEBIUS_PRICING["default"])
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 8)


class NebiusAdapter(BaseProviderAdapter):
    """
    Provider adapter for Nebius AI Cloud with NVIDIA Nemotron models.

    Uses httpx with an async client — NO openai SDK dependency.
    The Nebius API is OpenAI-compatible, so we speak the protocol directly.
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "nebius"

    @property
    def is_enabled(self) -> bool:
        return settings.NEBIUS_ENABLED and bool(settings.NEBIUS_API_KEY)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=settings.NEBIUS_BASE_URL,
                headers={
                    "Authorization": f"Bearer {settings.NEBIUS_API_KEY}",
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
        """Resolve the model to use for this request."""
        if request.preferred_model:
            return request.preferred_model
        return settings.NEBIUS_DEFAULT_MODEL

    def _build_payload(self, request: GatewayRequest, model: str) -> dict[str, Any]:
        """Build the OpenAI-compatible request payload."""
        return {
            "model": model,
            "messages": [
                {"role": msg.role.value, "content": msg.content}
                for msg in request.messages
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": False,
        }

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        model = self._resolve_model(request)
        payload = self._build_payload(request, model)
        client = self._get_client()

        start_ms = self._now_ms()
        request_id = str(uuid.uuid4())

        logger.info(
            "nebius.complete",
            model=model,
            request_id=request_id,
            project_id=request.project_id,
            experiment_id=request.experiment_id,
        )

        try:
            response = await client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(
                provider="nebius", timeout=settings.MODEL_GATEWAY_TIMEOUT
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(provider="nebius") from exc

        latency_ms = self._now_ms() - start_ms

        await self._handle_error_response(response)

        data = response.json()
        choice = data["choices"][0]
        usage_data = data.get("usage", {})

        prompt_tokens = usage_data.get("prompt_tokens", 0)
        completion_tokens = usage_data.get("completion_tokens", 0)

        is_missing = "prompt_tokens" not in usage_data and "completion_tokens" not in usage_data

        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=usage_data.get("total_tokens", prompt_tokens + completion_tokens),
            is_missing=is_missing,
            known_cost_usd=None if is_missing else _estimate_cost(model, prompt_tokens, completion_tokens),
        )

        logger.info(
            "nebius.complete.done",
            model=model,
            request_id=request_id,
            latency_ms=round(latency_ms, 2),
            tokens=usage.total_tokens,
            cost_usd=_estimate_cost(model, prompt_tokens, completion_tokens),
        )

        message = choice.get("message", {})

        # Robust extraction strategy
        raw_content = message.get("content")
        reasoning_content = message.get("reasoning_content")

        # If content is None or empty but reasoning exists, format it
        if not raw_content and reasoning_content:
            extracted_content = f"<reasoning>\n{reasoning_content}\n</reasoning>"
        elif not raw_content:
            # Check if there is some other structured content or it's genuinely malformed
            extracted_content = ""
        else:
            extracted_content = str(raw_content)

            # If both are present, we might want to combine them if they aren't already
            if reasoning_content and "<reasoning>" not in extracted_content:
                 extracted_content = f"<reasoning>\n{reasoning_content}\n</reasoning>\n\n{extracted_content}"

        if not extracted_content.strip():
            logger.warning(
                "nebius.complete.empty_response",
                model=model,
                request_id=request_id,
                message_keys=list(message.keys())
            )
            raise GatewayError(
                "Model returned empty or missing content",
                code="EMPTY_MODEL_RESPONSE"
            )

        return GatewayResponse(
            content=extracted_content,
            provider=Provider.NEBIUS,
            model=model,
            usage=usage,
            latency_ms=round(latency_ms, 2),
            request_id=request_id,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def stream(self, request: GatewayRequest) -> AsyncIterator[str]:
        """Stream tokens from Nebius (SSE protocol)."""
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
                        import json
                        try:
                            data = json.loads(chunk)
                            delta = data["choices"][0].get("delta", {})
                            if content := delta.get("content"):
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(
                provider="nebius", timeout=settings.MODEL_GATEWAY_TIMEOUT
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(provider="nebius") from exc

    async def health_check(self) -> ProviderHealth:
        """Lightweight health check — attempt a minimal completion."""
        import datetime

        if not self.is_enabled:
            return ProviderHealth(
                provider=Provider.NEBIUS,
                is_healthy=False,
                last_checked_at=datetime.datetime.utcnow().isoformat(),
                message="Provider disabled or API key not set",
            )

        from app.schemas.gateway import GatewayRequest, Message, MessageRole, TaskType

        probe_request = GatewayRequest(
            task_type=TaskType.GENERAL,
            messages=[Message(role=MessageRole.USER, content="ping")],
            preferred_model=settings.NEBIUS_FAST_MODEL,
            max_tokens=5,
            temperature=0.0,
        )

        start_ms = self._now_ms()
        try:
            await self.complete(probe_request)
            latency_ms = self._now_ms() - start_ms
            return ProviderHealth(
                provider=Provider.NEBIUS,
                is_healthy=True,
                last_checked_at=datetime.datetime.utcnow().isoformat(),
                avg_latency_ms=round(latency_ms, 2),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(
                provider=Provider.NEBIUS,
                is_healthy=False,
                last_checked_at=datetime.datetime.utcnow().isoformat(),
                message=str(exc)[:200],
            )

    @staticmethod
    async def _handle_error_response(response: httpx.Response) -> None:
        """Map HTTP error codes to AerowindError subclasses."""
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
                provider="nebius",
                retry_after=float(retry_after) if retry_after else None,
            )
        if response.status_code == 402:
            raise QuotaExceededError(provider="nebius")
        if response.status_code == 404:
            raise ModelNotFoundError(model="unknown", provider="nebius")
        if response.status_code in (502, 503, 504):
            raise ProviderUnavailableError(provider="nebius")

        raise GatewayError(
            f"Nebius API error {response.status_code}: {body[:300]}",
            code="NEBIUS_API_ERROR",
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
