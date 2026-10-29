"""
AEROWIND — Provider Health Monitor
=====================================
Tracks the health of each provider in a background task.
The ModelGateway queries this before routing requests.
"""

from __future__ import annotations

import asyncio
import datetime
from collections import defaultdict, deque

from app.core.logging import get_logger
from app.schemas.gateway import Provider, ProviderHealth

logger = get_logger(__name__)

_HEALTH_CHECK_INTERVAL = 60  # seconds
_LATENCY_WINDOW = 20  # last N successful calls for rolling average
_FAILURE_THRESHOLD = 3  # consecutive failures → unhealthy


class ProviderHealthMonitor:
    """
    Maintains a real-time health snapshot for all providers.

    Agents and the gateway use is_healthy() to avoid dead providers.
    A background asyncio task calls _run_checks() periodically.
    """

    def __init__(self) -> None:
        # Latest health per provider
        self._health: dict[Provider, ProviderHealth] = {}
        # Rolling latency measurements (for avg)
        self._latency_window: dict[Provider, deque[float]] = defaultdict(
            lambda: deque(maxlen=_LATENCY_WINDOW)
        )
        # Consecutive failure counter
        self._consecutive_failures: dict[Provider, int] = defaultdict(int)
        # Background task handle
        self._task: asyncio.Task[None] | None = None

    def start(self, adapters: dict[Provider, object]) -> None:
        """Start the background health check loop."""
        self._adapters = adapters
        self._task = asyncio.create_task(self._run_checks(), name="health-monitor")
        logger.info("health_monitor.started")

    async def stop(self) -> None:
        """Cancel the background health check loop."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("health_monitor.stopped")

    def is_healthy(self, provider: Provider) -> bool:
        """Return True if the provider is currently considered healthy."""
        health = self._health.get(provider)
        if health is None:
            # Not yet checked — assume healthy for graceful startup
            return True
        return health.is_healthy

    def get_healthy_providers(self) -> set[Provider]:
        """Return set of currently healthy providers."""
        return {p for p in Provider if self.is_healthy(p)}

    def get_all_health(self) -> list[ProviderHealth]:
        """Return all health snapshots."""
        return list(self._health.values())

    def record_success(self, provider: Provider, latency_ms: float) -> None:
        """Record a successful request (called by gateway after each call)."""
        self._consecutive_failures[provider] = 0
        self._latency_window[provider].append(latency_ms)
        # Update rolling avg in existing health
        if provider in self._health:
            window = self._latency_window[provider]
            self._health[provider].avg_latency_ms = round(
                sum(window) / len(window), 2
            )
            self._health[provider].is_healthy = True
            self._health[provider].consecutive_failures = 0

    def record_failure(self, provider: Provider) -> None:
        """Record a failed request (called by gateway after each error)."""
        self._consecutive_failures[provider] += 1
        fails = self._consecutive_failures[provider]
        if provider in self._health:
            self._health[provider].consecutive_failures = fails
            if fails >= _FAILURE_THRESHOLD:
                self._health[provider].is_healthy = False
                logger.warning(
                    "health_monitor.provider_unhealthy",
                    provider=provider,
                    consecutive_failures=fails,
                )

    async def _run_checks(self) -> None:
        """Background loop — runs health checks on all providers."""
        while True:
            await asyncio.sleep(_HEALTH_CHECK_INTERVAL)
            for provider, adapter in self._adapters.items():
                try:
                    health: ProviderHealth = await adapter.health_check()  # type: ignore[attr-defined]
                    self._health[provider] = health
                    logger.debug(
                        "health_monitor.check",
                        provider=provider,
                        healthy=health.is_healthy,
                        latency_ms=health.avg_latency_ms,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "health_monitor.check_failed",
                        provider=provider,
                        error=str(exc),
                    )
                    self._health[provider] = ProviderHealth(
                        provider=provider,
                        is_healthy=False,
                        last_checked_at=datetime.datetime.utcnow().isoformat(),
                        message=str(exc)[:200],
                    )
