"""
AEROWIND — Gateway Usage Tracker
==================================
Tracks token usage, request counts, costs, and latency per:
- Provider
- Project
- Experiment
- Agent

In Phase 3 this will persist to PostgreSQL.
For Phase 1/2, it maintains an in-memory store.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.schemas.gateway import GatewayResponse, Provider

logger = get_logger(__name__)

# Cost per 1M tokens by provider (blended estimate; real costs tracked per model)
_PROVIDER_COST_PER_M_TOKENS: dict[Provider, float] = {
    Provider.NEBIUS: 0.26,
    Provider.OPENAI: 0.375,
    Provider.ANTHROPIC: 7.50,
    Provider.GEMINI: 0.19,
}


@dataclass
class UsageBucket:
    """Aggregated usage statistics for a single dimension."""

    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    failures: int = 0
    latency_samples: list[float] = field(default_factory=list)

    @property
    def avg_latency_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        return round(sum(self.latency_samples) / len(self.latency_samples), 2)

    @property
    def p95_latency_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        sorted_samples = sorted(self.latency_samples)
        idx = max(0, int(len(sorted_samples) * 0.95) - 1)
        return round(sorted_samples[idx], 2)


class UsageTracker:
    """
    Thread-safe usage aggregation across providers, projects, and experiments.

    Phase 1: In-memory only.
    Phase 3: Will flush to PostgreSQL periodically.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # Keyed by provider
        self._by_provider: dict[Provider, UsageBucket] = defaultdict(UsageBucket)
        # Keyed by project_id
        self._by_project: dict[str, UsageBucket] = defaultdict(UsageBucket)
        # Keyed by experiment_id
        self._by_experiment: dict[str, UsageBucket] = defaultdict(UsageBucket)
        # Global totals
        self._global = UsageBucket()

    async def record(self, response: GatewayResponse, project_id: str | None = None,
                     experiment_id: str | None = None) -> None:
        """Record a successful gateway response."""
        async with self._lock:
            cost = self._estimate_cost(response)

            for bucket in self._get_buckets(response.provider, project_id, experiment_id):
                bucket.requests += 1
                bucket.prompt_tokens += response.usage.prompt_tokens
                bucket.completion_tokens += response.usage.completion_tokens
                bucket.total_tokens += response.usage.total_tokens
                bucket.estimated_cost_usd += cost
                bucket.total_latency_ms += response.latency_ms
                bucket.latency_samples.append(response.latency_ms)
                # Keep latency window bounded
                if len(bucket.latency_samples) > 1000:
                    bucket.latency_samples = bucket.latency_samples[-500:]

        logger.debug(
            "usage.recorded",
            provider=response.provider,
            tokens=response.usage.total_tokens,
            cost_usd=cost,
            latency_ms=response.latency_ms,
            project_id=project_id,
            experiment_id=experiment_id,
        )

    async def record_failure(self, provider: Provider, project_id: str | None = None,
                             experiment_id: str | None = None) -> None:
        """Record a failed gateway request."""
        async with self._lock:
            for bucket in self._get_buckets(provider, project_id, experiment_id):
                bucket.failures += 1

    def get_global_stats(self) -> dict[str, object]:
        """Return global usage statistics."""
        return {
            "total_requests": self._global.requests,
            "total_tokens": self._global.total_tokens,
            "total_prompt_tokens": self._global.prompt_tokens,
            "total_completion_tokens": self._global.completion_tokens,
            "estimated_cost_usd": round(self._global.estimated_cost_usd, 6),
            "avg_latency_ms": self._global.avg_latency_ms,
            "p95_latency_ms": self._global.p95_latency_ms,
            "total_failures": self._global.failures,
        }

    def get_provider_stats(self, provider: Provider) -> dict[str, object]:
        """Return usage statistics for a specific provider."""
        bucket = self._by_provider.get(provider, UsageBucket())
        return {
            "provider": provider,
            "requests": bucket.requests,
            "total_tokens": bucket.total_tokens,
            "estimated_cost_usd": round(bucket.estimated_cost_usd, 6),
            "avg_latency_ms": bucket.avg_latency_ms,
            "p95_latency_ms": bucket.p95_latency_ms,
            "failures": bucket.failures,
        }

    def get_experiment_stats(self, experiment_id: str) -> dict[str, object]:
        """Return usage statistics for a specific experiment."""
        bucket = self._by_experiment.get(experiment_id, UsageBucket())
        return {
            "experiment_id": experiment_id,
            "requests": bucket.requests,
            "total_tokens": bucket.total_tokens,
            "estimated_cost_usd": round(bucket.estimated_cost_usd, 6),
            "avg_latency_ms": bucket.avg_latency_ms,
            "p95_latency_ms": bucket.p95_latency_ms,
            "failures": bucket.failures,
        }

    def _get_buckets(
        self, provider: Provider, project_id: str | None, experiment_id: str | None
    ) -> list[UsageBucket]:
        buckets = [self._global, self._by_provider[provider]]
        if project_id:
            buckets.append(self._by_project[project_id])
        if experiment_id:
            buckets.append(self._by_experiment[experiment_id])
        return buckets

    @staticmethod
    def _estimate_cost(response: GatewayResponse) -> float:
        rate = _PROVIDER_COST_PER_M_TOKENS.get(response.provider, 1.0)
        return round((response.usage.total_tokens / 1_000_000) * rate, 8)
