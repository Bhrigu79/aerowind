import pytest
import json
import httpx
from unittest.mock import patch, AsyncMock, MagicMock

from app.db.models import (
    ExperimentRun, ExperimentVariant, MetricResult, Constraint
)
from app.gateway.gateway import ModelGateway
from app.gateway.adapters.nebius import NebiusAdapter
from app.core.exceptions import GatewayTimeoutError, NoProvidersAvailableError
from app.services.ai_benchmark import RealAIBenchmarkRunner
from app.schemas.gateway import Provider, GatewayRequest, TaskType
from app.db.database import async_session_maker
from app.domain.types import MetricDirection
from app.services.constraints import ConstraintEngine

@pytest.fixture
def mock_httpx():
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client_class.return_value = mock_client
        yield mock_client

@pytest.fixture
def run_fixture():
    run = ExperimentRun(
        id="run_targeted",
        experiment_id="exp_123",
        variant_id="var_123",
        status="pending",
        execution_provenance="REAL_EXECUTION",
    )
    return run

@pytest.fixture
def variant_fixture():
    return ExperimentVariant(
        id="var_123",
        project_id="proj_1",
        system_configuration={"temperature": 0.0, "max_tokens": 10, "model": "nvidia/llama-3.1-nemotron-70b-instruct", "provider": "nebius", "sample_count": 1}
    )

@pytest.mark.asyncio
async def test_usage_missing_yields_unavailable_cost(mock_httpx, run_fixture, variant_fixture):
    # R1: usage missing -> cost unavailable (None), NOT zero
    mock_response = MagicMock()
    mock_response.status_code = 200
    # Provide no usage metadata
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "positive"}, "finish_reason": "stop"}]
    }
    mock_httpx.post.return_value = mock_response

    adapter = NebiusAdapter()
    req = GatewayRequest(task_type=TaskType.CLASSIFICATION, messages=[], preferred_model="x")
    resp = await adapter.complete(req)

    assert resp.usage.is_missing is True
    assert resp.usage.estimated_cost_usd is None

@pytest.mark.asyncio
async def test_missing_cost_cannot_falsely_satisfy_constraint():
    # R3: missing cost cannot falsely satisfy a cost constraint
    # R4: no fabricated cost reaches DecisionEngine
    c = Constraint(project_id="proj_1", metric_name="cost_per_request_usd", operator="<=", required_value=0.01)

    # We simulate RealAIBenchmarkRunner producing NO cost metric because cost was None
    # So candidate_metrics has no cost metric
    metrics = [
        MetricResult(metric_name="quality_score", value=95.0, direction=MetricDirection.HIGHER_IS_BETTER.value, run_id="run_123")
    ]

    evals = ConstraintEngine.evaluate([c], metrics)
    assert len(evals) == 1
    # Constraint fails because cost metric is missing from evidence
    assert evals[0].passed is False

@pytest.mark.asyncio
async def test_real_benchmark_omits_missing_cost(run_fixture, variant_fixture):
    # Prove that the runner itself omits the metric if cost is missing
    gateway = ModelGateway()

    mock_resp = AsyncMock()
    mock_resp.content = "positive"
    # Set missing cost on the mock GatewayResponse
    mock_resp.usage = MagicMock()
    # Explicitly set to None to simulate missing usage
    mock_resp.usage.estimated_cost_usd = None

    gateway.complete = AsyncMock(return_value=mock_resp)

    runner = RealAIBenchmarkRunner(gateway)

    async with async_session_maker() as session:
        mock_session = AsyncMock()
        mock_session.get.return_value = variant_fixture

        # We also mock session.add to catch which metrics are stored
        added_metrics = []
        def mock_add(m):
            if isinstance(m, MetricResult):
                added_metrics.append(m)
        mock_session.add.side_effect = mock_add

        await runner.execute(mock_session, run_fixture)

        cost_metrics = [m for m in added_metrics if m.metric_name == "cost_per_request_usd"]
        assert len(cost_metrics) == 0  # Should be omitted

@pytest.mark.asyncio
async def test_nebius_fail_closed_routing():
    # R2: Nebius unavailable -> no silent provider substitution
    # If generic routing is on, GatewayRequest with allow_fallback=False must raise
    gateway = ModelGateway()

    # Mock health check to say NEBIUS is healthy, so we can reach complete() execution
    gateway._health_monitor.get_healthy_providers = MagicMock(return_value={Provider.NEBIUS})

    with patch('app.gateway.gateway.settings') as mock_settings:
        mock_settings.enabled_providers = ["nebius"]

        # Simulate Nebius raising a timeout
        req = GatewayRequest(
            task_type=TaskType.CLASSIFICATION,
            messages=[],
            preferred_provider=Provider.NEBIUS,
            allow_fallback=False
        )

        # Mock primary provider to fail
        with patch.object(gateway, '_execute_with_retry', side_effect=GatewayTimeoutError("Timeout", timeout=10.0)):
            with pytest.raises(GatewayTimeoutError):
                await gateway.complete(req)

@pytest.mark.asyncio
async def test_runner_enforces_fail_closed(run_fixture, variant_fixture):
    # Ensure RealAIBenchmarkRunner sets allow_fallback=False
    gateway = ModelGateway()

    async def mock_complete(req: GatewayRequest):
        assert req.allow_fallback is False
        raise NoProvidersAvailableError()

    gateway.complete = AsyncMock(side_effect=mock_complete)

    runner = RealAIBenchmarkRunner(gateway)

    async with async_session_maker() as session:
        mock_session = AsyncMock()
        mock_session.get.return_value = variant_fixture

        with pytest.raises(Exception):
            await runner.execute(mock_session, run_fixture)
