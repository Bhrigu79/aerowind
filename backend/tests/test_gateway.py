"""
AEROWIND Gateway Tests
=======================
Tests for the Model Gateway, router, and adapters.
These tests do NOT require real API keys — they test the internal logic.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.gateway.router import ModelRouter
from app.schemas.gateway import (
    GatewayRequest,
    GatewayResponse,
    Message,
    MessageRole,
    Provider,
    TaskType,
    TokenUsage,
)


def _make_request(
    task: TaskType = TaskType.GENERAL,
    preferred_provider: Provider | None = None,
    preferred_model: str | None = None,
) -> GatewayRequest:
    return GatewayRequest(
        task_type=task,
        messages=[Message(role=MessageRole.USER, content="test")],
        preferred_provider=preferred_provider,
        preferred_model=preferred_model,
    )


def _make_response(provider: Provider = Provider.NEBIUS) -> GatewayResponse:
    return GatewayResponse(
        content="test response",
        provider=provider,
        model="test-model",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        latency_ms=100.0,
        request_id="test-req-123",
    )


class TestModelRouter:
    def test_routes_reasoning_to_nebius_first(self) -> None:
        router = ModelRouter(healthy_providers={Provider.NEBIUS, Provider.OPENAI})
        provider, model = router.route(_make_request(task=TaskType.REASONING))
        assert provider == Provider.NEBIUS
        assert model is not None  # Model should be set for Nebius

    def test_routes_to_openai_when_nebius_unhealthy(self) -> None:
        router = ModelRouter(healthy_providers={Provider.OPENAI})
        provider, model = router.route(_make_request(task=TaskType.REASONING))
        assert provider == Provider.OPENAI

    def test_explicit_provider_override(self) -> None:
        router = ModelRouter(healthy_providers={Provider.NEBIUS, Provider.OPENAI})
        request = _make_request(preferred_provider=Provider.OPENAI, preferred_model="gpt-4o")
        provider, model = router.route(request)
        assert provider == Provider.OPENAI
        assert model == "gpt-4o"

    def test_raises_when_no_healthy_providers(self) -> None:
        router = ModelRouter(healthy_providers=set())
        with pytest.raises(RuntimeError, match="No healthy providers"):
            router.route(_make_request())

    def test_classification_routes_to_fast_model(self) -> None:
        router = ModelRouter(healthy_providers={Provider.NEBIUS})
        provider, model = router.route(_make_request(task=TaskType.CLASSIFICATION))
        assert provider == Provider.NEBIUS
        # Fast model should be selected for classification
        assert model is not None

    def test_all_task_types_have_routes(self) -> None:
        router = ModelRouter(healthy_providers={Provider.NEBIUS})
        for task_type in TaskType:
            provider, model = router.route(_make_request(task=task_type))
            assert provider == Provider.NEBIUS


class TestUsageTracker:
    @pytest.mark.asyncio
    async def test_records_response(self) -> None:
        from app.gateway.usage import UsageTracker
        tracker = UsageTracker()
        response = _make_response()
        await tracker.record(response, project_id="proj-1", experiment_id="exp-1")
        stats = tracker.get_global_stats()
        assert stats["total_requests"] == 1
        assert stats["total_tokens"] == 30

    @pytest.mark.asyncio
    async def test_records_failure(self) -> None:
        from app.gateway.usage import UsageTracker
        tracker = UsageTracker()
        await tracker.record_failure(Provider.NEBIUS, project_id="proj-1")
        stats = tracker.get_global_stats()
        assert stats["total_failures"] == 1

    @pytest.mark.asyncio
    async def test_per_experiment_tracking(self) -> None:
        from app.gateway.usage import UsageTracker
        tracker = UsageTracker()
        response = _make_response()
        await tracker.record(response, experiment_id="exp-42")
        exp_stats = tracker.get_experiment_stats("exp-42")
        assert exp_stats["requests"] == 1
        assert exp_stats["total_tokens"] == 30


class TestGatewaySchemas:
    def test_gateway_request_serialization(self) -> None:
        request = _make_request()
        data = request.model_dump()
        assert data["task_type"] == "general"
        assert len(data["messages"]) == 1

    def test_task_type_values(self) -> None:
        assert TaskType.REASONING == "reasoning"
        assert TaskType.CODE_GENERATION == "code_generation"

    def test_provider_values(self) -> None:
        assert Provider.NEBIUS == "nebius"
        assert Provider.OPENAI == "openai"
        assert Provider.ANTHROPIC == "anthropic"
        assert Provider.GEMINI == "gemini"

    def test_token_usage_cost_estimate(self) -> None:
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        # At $0.50/1M tokens, 1500 tokens = $0.00000075
        assert usage.estimated_cost_usd > 0


class TestHealthMonitor:
    def test_assumes_healthy_before_first_check(self) -> None:
        from app.gateway.health import ProviderHealthMonitor
        monitor = ProviderHealthMonitor()
        assert monitor.is_healthy(Provider.NEBIUS) is True

    def test_records_consecutive_failures(self) -> None:
        from app.gateway.health import ProviderHealthMonitor, _FAILURE_THRESHOLD
        monitor = ProviderHealthMonitor()
        # Need a health entry first
        import datetime
        from app.schemas.gateway import ProviderHealth
        monitor._health[Provider.NEBIUS] = ProviderHealth(
            provider=Provider.NEBIUS,
            is_healthy=True,
            last_checked_at=datetime.datetime.utcnow().isoformat(),
        )
        for _ in range(_FAILURE_THRESHOLD):
            monitor.record_failure(Provider.NEBIUS)
        assert monitor.is_healthy(Provider.NEBIUS) is False

    def test_success_clears_failures(self) -> None:
        from app.gateway.health import ProviderHealthMonitor, _FAILURE_THRESHOLD
        monitor = ProviderHealthMonitor()
        import datetime
        from app.schemas.gateway import ProviderHealth
        monitor._health[Provider.NEBIUS] = ProviderHealth(
            provider=Provider.NEBIUS,
            is_healthy=False,
            last_checked_at=datetime.datetime.utcnow().isoformat(),
        )
        monitor._consecutive_failures[Provider.NEBIUS] = _FAILURE_THRESHOLD
        monitor.record_success(Provider.NEBIUS, latency_ms=150.0)
        assert monitor.is_healthy(Provider.NEBIUS) is True
