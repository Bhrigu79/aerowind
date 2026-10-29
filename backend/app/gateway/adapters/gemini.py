"""
AEROWIND — Google Gemini Provider Adapter
==========================================
Uses Gemini's generateContent REST API via raw httpx.
Maps Gemini's parts-based message format to the provider-agnostic schema.
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

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

_GEMINI_PRICING: dict[str, dict[str, float]] = {
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.0-pro": {"input": 0.50, "output": 1.50},
    "default": {"input": 0.50, "output": 1.50},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    key = next((k for k in _GEMINI_PRICING if k in model), "default")
    pricing = _GEMINI_PRICING[key]
    return round(
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"],
        8,
    )


def _messages_to_gemini(messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
    """
    Convert provider-agnostic messages to Gemini's contents format.
    Gemini uses 'user' and 'model' roles and 'parts' structure.
    """
    system_instruction: str | None = None
    contents: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == MessageRole.SYSTEM:
            system_instruction = msg.content
        elif msg.role == MessageRole.USER:
            contents.append({"role": "user", "parts": [{"text": msg.content}]})
        elif msg.role == MessageRole.ASSISTANT:
            contents.append({"role": "model", "parts": [{"text": msg.content}]})

    return system_instruction, contents


class GeminiAdapter(BaseProviderAdapter):
    """Google Gemini adapter via raw httpx."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def is_enabled(self) -> bool:
        return settings.GEMINI_ENABLED and bool(settings.GEMINI_API_KEY)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=_GEMINI_BASE_URL,
                timeout=httpx.Timeout(
                    connect=10.0,
                    read=float(settings.MODEL_GATEWAY_TIMEOUT),
                    write=10.0,
                    pool=5.0,
                ),
            )
        return self._client

    def _resolve_model(self, request: GatewayRequest) -> str:
        return request.preferred_model or settings.GEMINI_DEFAULT_MODEL

    def _build_payload(self, request: GatewayRequest) -> dict[str, Any]:
        system_instruction, contents = _messages_to_gemini(request.messages)
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": request.max_tokens,
                "temperature": request.temperature,
                "topP": request.top_p,
            },
        }
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        return payload

    def _url_for(self, model: str, action: str = "generateContent") -> str:
        return f"/models/{model}:{action}?key={settings.GEMINI_API_KEY}"

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        model = self._resolve_model(request)
        payload = self._build_payload(request)
        client = self._get_client()
        start_ms = self._now_ms()
        request_id = str(uuid.uuid4())

        try:
            response = await client.post(self._url_for(model), json=payload)
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(
                provider="gemini", timeout=settings.MODEL_GATEWAY_TIMEOUT
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(provider="gemini") from exc

        latency_ms = self._now_ms() - start_ms
        await self._handle_error_response(response)

        data = response.json()
        candidate = data["candidates"][0]
        text = "".join(
            part.get("text", "")
            for part in candidate.get("content", {}).get("parts", [])
        )

        usage_data = data.get("usageMetadata", {})
        input_tokens = usage_data.get("promptTokenCount", 0)
        output_tokens = usage_data.get("candidatesTokenCount", 0)

        return GatewayResponse(
            content=text,
            provider=Provider.GEMINI,
            model=model,
            usage=TokenUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=usage_data.get("totalTokenCount", input_tokens + output_tokens),
            ),
            latency_ms=round(latency_ms, 2),
            request_id=request_id,
            finish_reason=candidate.get("finishReason", "STOP").lower(),
        )

    async def stream(self, request: GatewayRequest) -> AsyncIterator[str]:
        model = self._resolve_model(request)
        payload = self._build_payload(request)
        client = self._get_client()

        try:
            async with client.stream(
                "POST", self._url_for(model, "streamGenerateContent"), json=payload
            ) as response:
                await self._handle_error_response(response)
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    # Gemini streams newline-delimited JSON
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line or line in ("[", "]", ","):
                            continue
                        try:
                            data = json.loads(line.lstrip(","))
                            candidate = data.get("candidates", [{}])[0]
                            for part in candidate.get("content", {}).get("parts", []):
                                if text := part.get("text"):
                                    yield text
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(
                provider="gemini", timeout=settings.MODEL_GATEWAY_TIMEOUT
            ) from exc

    async def health_check(self) -> ProviderHealth:
        import datetime

        if not self.is_enabled:
            return ProviderHealth(
                provider=Provider.GEMINI,
                is_healthy=False,
                last_checked_at=datetime.datetime.utcnow().isoformat(),
                message="Provider disabled or API key not set",
            )

        probe = GatewayRequest(  # type: ignore[call-arg]
            task_type="general",
            messages=[Message(role=MessageRole.USER, content="ping")],
            max_tokens=5,
            temperature=0.0,
        )
        start_ms = self._now_ms()
        try:
            await self.complete(probe)
            return ProviderHealth(
                provider=Provider.GEMINI,
                is_healthy=True,
                last_checked_at=datetime.datetime.utcnow().isoformat(),
                avg_latency_ms=round(self._now_ms() - start_ms, 2),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(
                provider=Provider.GEMINI,
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
            raise RateLimitError(provider="gemini")
        if response.status_code == 402:
            raise QuotaExceededError(provider="gemini")
        if response.status_code == 404:
            raise ModelNotFoundError(model="unknown", provider="gemini")
        if response.status_code in (502, 503, 504):
            raise ProviderUnavailableError(provider="gemini")

        raise GatewayError(
            f"Gemini API error {response.status_code}: {body[:300]}",
            code="GEMINI_API_ERROR",
        )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
