"""
AEROWIND — Model Gateway
==========================
THE central abstraction between agents and model providers.

Agents NEVER import provider adapters or SDK clients directly.
All model calls flow through ModelGateway.complete() or ModelGateway.stream().

Responsibilities:
- Provider selection (via ModelRouter)
- Retries with exponential backoff (via tenacity)
- Rate limit / quota handling
- Timeout enforcement
- Provider health tracking
- Usage recording
- Fallback to secondary providers
- Task-aware routing
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.exceptions import (
    GatewayError,
    GatewayTimeoutError,
    NoProvidersAvailableError,
    ProviderUnavailableError,
    RateLimitError,
)
from app.core.logging import get_logger
from app.gateway.adapters.anthropic import AnthropicAdapter
from app.gateway.adapters.base import BaseProviderAdapter
from app.gateway.adapters.gemini import GeminiAdapter
from app.gateway.adapters.nebius import NebiusAdapter
from app.gateway.adapters.openai import OpenAIAdapter
from app.gateway.health import ProviderHealthMonitor
from app.gateway.router import ModelRouter
from app.gateway.usage import UsageTracker
from app.schemas.gateway import (
    GatewayRequest,
    GatewayResponse,
    GatewayStatus,
    Provider,
    ProviderHealth,
)

logger = get_logger(__name__)


class ModelGateway:
    """
    The single point of entry for all model inference.

    Usage from agents:
        response = await gateway.complete(request)

    The gateway handles all provider-level complexity transparently.
    """

    def __init__(self) -> None:
        # Initialize all provider adapters
        self._adapters: dict[Provider, BaseProviderAdapter] = {
            Provider.NEBIUS: NebiusAdapter(),
            Provider.OPENAI: OpenAIAdapter(),
            Provider.ANTHROPIC: AnthropicAdapter(),
            Provider.GEMINI: GeminiAdapter(),
        }
        self._health_monitor = ProviderHealthMonitor()
        self._usage_tracker = UsageTracker()
        self._initialized = False

    async def initialize(self) -> None:
        """
        Called on application startup.
        Starts the health monitor background task.
        """
        if self._initialized:
            return

        # Mark initially enabled providers as healthy (will be checked shortly)
        enabled = settings.enabled_providers
        logger.info("gateway.initializing", enabled_providers=enabled)

        # Start background health monitor
        adapter_map = {
            Provider(name): adapter
            for name, adapter in [
                ("nebius", self._adapters[Provider.NEBIUS]),
                ("openai", self._adapters[Provider.OPENAI]),
                ("anthropic", self._adapters[Provider.ANTHROPIC]),
                ("gemini", self._adapters[Provider.GEMINI]),
            ]
            if name in enabled
        }
        self._health_monitor.start(adapter_map)
        self._initialized = True
        logger.info("gateway.initialized")

    async def shutdown(self) -> None:
        """Called on application shutdown. Cleans up resources."""
        await self._health_monitor.stop()
        # Close all HTTP clients
        for adapter in self._adapters.values():
            if hasattr(adapter, "close"):
                await adapter.close()  # type: ignore[attr-defined]
        logger.info("gateway.shutdown")

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        """
        Execute a completion request with automatic routing, retries, and fallback.

        Args:
            request: Provider-agnostic GatewayRequest

        Returns:
            Provider-agnostic GatewayResponse

        Raises:
            NoProvidersAvailableError: If all providers fail
            GatewayError: For non-retryable errors
        """
        healthy = self._health_monitor.get_healthy_providers()

        # Filter to only enabled providers
        enabled = {Provider(p) for p in settings.enabled_providers}
        healthy = healthy & enabled

        if not healthy:
            raise NoProvidersAvailableError()

        router = ModelRouter(healthy_providers=healthy)

        try:
            provider, model_override = router.route(request)
        except RuntimeError:
            raise NoProvidersAvailableError()

        # Apply model override from router
        if model_override and not request.preferred_model:
            request = request.model_copy(update={"preferred_model": model_override})

        # Try primary provider with retries
        try:
            return await self._execute_with_retry(provider, request)
        except (ProviderUnavailableError, GatewayTimeoutError, RateLimitError) as primary_exc:
            logger.warning(
                "gateway.primary_failed_trying_fallback",
                primary_provider=provider,
                error=str(primary_exc),
            )
            if not request.allow_fallback:
                raise primary_exc
            # Try fallback providers
            return await self._try_fallback(provider, request, healthy)

    async def stream(self, request: GatewayRequest) -> AsyncIterator[str]:
        """
        Stream tokens with the same routing logic as complete().
        Yields token strings as they arrive.
        """
        healthy = self._health_monitor.get_healthy_providers()
        enabled = {Provider(p) for p in settings.enabled_providers}
        healthy = healthy & enabled

        if not healthy:
            raise NoProvidersAvailableError()

        router = ModelRouter(healthy_providers=healthy)
        try:
            provider, model_override = router.route(request)
        except RuntimeError:
            raise NoProvidersAvailableError()

        if model_override and not request.preferred_model:
            request = request.model_copy(update={"preferred_model": model_override})

        adapter = self._adapters[provider]
        async for token in adapter.stream(request):
            yield token

    async def get_status(self) -> GatewayStatus:
        """Return a full gateway status snapshot for the /health endpoint."""
        all_health = self._health_monitor.get_all_health()

        # Fill in any providers not yet checked
        checked = {h.provider for h in all_health}
        import datetime
        for provider in Provider:
            if provider not in checked:
                adapter = self._adapters[provider]
                all_health.append(
                    ProviderHealth(
                        provider=provider,
                        is_healthy=adapter.is_enabled,
                        last_checked_at=datetime.datetime.utcnow().isoformat(),
                        message="Not yet checked" if adapter.is_enabled else "Disabled",
                    )
                )

        global_stats = self._usage_tracker.get_global_stats()
        return GatewayStatus(
            default_provider=Provider(settings.MODEL_GATEWAY_DEFAULT_PROVIDER),
            providers=all_health,
            total_requests=global_stats["total_requests"],  # type: ignore[arg-type]
            total_tokens=global_stats["total_tokens"],  # type: ignore[arg-type]
            estimated_cost_usd=global_stats["estimated_cost_usd"],  # type: ignore[arg-type]
        )

    @property
    def usage_tracker(self) -> UsageTracker:
        return self._usage_tracker

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _execute_with_retry(
        self, provider: Provider, request: GatewayRequest
    ) -> GatewayResponse:
        """Execute a request against a specific provider with retry logic."""
        adapter = self._adapters[provider]

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(settings.MODEL_GATEWAY_MAX_RETRIES),
            wait=wait_exponential(
                multiplier=settings.MODEL_GATEWAY_RETRY_DELAY, min=1, max=30
            ),
            retry=retry_if_exception_type((RateLimitError, GatewayTimeoutError)),
            reraise=True,
        ):
            with attempt:
                try:
                    response = await asyncio.wait_for(
                        adapter.complete(request),
                        timeout=float(settings.MODEL_GATEWAY_TIMEOUT),
                    )
                    # Record success
                    self._health_monitor.record_success(provider, response.latency_ms)
                    await self._usage_tracker.record(
                        response,
                        project_id=request.project_id,
                        experiment_id=request.experiment_id,
                    )
                    return response

                except asyncio.TimeoutError as exc:
                    self._health_monitor.record_failure(provider)
                    await self._usage_tracker.record_failure(
                        provider,
                        project_id=request.project_id,
                        experiment_id=request.experiment_id,
                    )
                    raise GatewayTimeoutError(
                        provider=provider, timeout=settings.MODEL_GATEWAY_TIMEOUT
                    ) from exc

                except (RateLimitError, GatewayTimeoutError):
                    self._health_monitor.record_failure(provider)
                    raise

                except Exception as exc:
                    self._health_monitor.record_failure(provider)
                    await self._usage_tracker.record_failure(
                        provider,
                        project_id=request.project_id,
                        experiment_id=request.experiment_id,
                    )
                    logger.error(
                        "gateway.request_failed",
                        provider=provider,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
                    raise

        # Should never reach here — tenacity reraises
        raise GatewayError("Retry loop exhausted", code="RETRY_EXHAUSTED")

    async def _try_fallback(
        self,
        failed_provider: Provider,
        request: GatewayRequest,
        healthy: set[Provider],
    ) -> GatewayResponse:
        """Attempt request on alternative providers after primary fails."""
        fallback_candidates = [p for p in healthy if p != failed_provider]

        if not fallback_candidates:
            raise NoProvidersAvailableError()

        for fallback_provider in fallback_candidates:
            logger.info(
                "gateway.trying_fallback",
                fallback_provider=fallback_provider,
                failed_provider=failed_provider,
            )
            try:
                # Clear model override for fallback — use adapter defaults
                fallback_request = request.model_copy(
                    update={"preferred_provider": fallback_provider, "preferred_model": None}
                )
                response = await self._execute_with_retry(fallback_provider, fallback_request)
                # Mark response as fallback
                return response.model_copy(
                    update={"was_fallback": True, "fallback_from": failed_provider}
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "gateway.fallback_failed",
                    fallback_provider=fallback_provider,
                    error=str(exc),
                )
                continue

        raise NoProvidersAvailableError()


# ── Application-level singleton ───────────────────────────────────────────────

_gateway: ModelGateway | None = None


def get_gateway() -> ModelGateway:
    """Return the application-level ModelGateway singleton."""
    global _gateway
    if _gateway is None:
        _gateway = ModelGateway()
    return _gateway
