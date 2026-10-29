import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.services.nebius_runner import NebiusExperimentRunner
from app.services.runner import ExecutionFailure
from app.core.config import settings
from app.schemas.execution import ExperimentExecutionSpec, ResourceLimits
from app.db.models import ExperimentRun
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

def test_nebius_runner_disabled_by_default():
    assert not settings.NEBIUS_EXEC_ENABLED

    with pytest.raises(ValueError, match="Nebius execution is not enabled"):
        runner = NebiusExperimentRunner()

def test_nebius_runner_missing_credentials(monkeypatch):
    monkeypatch.setattr(settings, "NEBIUS_EXEC_ENABLED", True)
    monkeypatch.setattr(settings, "NEBIUS_EXEC_SERVICE_ACCOUNT_ID", "")

    with pytest.raises(ValueError, match="Nebius service account configuration is missing"):
        runner = NebiusExperimentRunner()

@pytest.fixture
def mock_runner(monkeypatch):
    monkeypatch.setattr(settings, "NEBIUS_EXEC_ENABLED", True)
    monkeypatch.setattr(settings, "NEBIUS_EXEC_SERVICE_ACCOUNT_ID", "mock-sa")
    monkeypatch.setattr(settings, "NEBIUS_EXEC_PUBLIC_KEY_ID", "mock-pub")
    monkeypatch.setattr(settings, "NEBIUS_EXEC_PRIVATE_KEY_FILE", "mock-priv")
    monkeypatch.setattr(settings, "NEBIUS_EXEC_PROJECT_ID", "mock-proj")

    import app.services.nebius_runner
    mock_sdk_cls = MagicMock()
    monkeypatch.setattr(app.services.nebius_runner, "SDK", mock_sdk_cls)

    runner = NebiusExperimentRunner()

    # Mock the client
    runner.client = MagicMock()
    return runner

@pytest.fixture
def mock_session():
    session = AsyncMock(spec=AsyncSession)
    return session

@pytest.fixture
def mock_run():
    run = ExperimentRun(id="run123", status="pending")
    run.execution_metadata = {}
    return run

@pytest.fixture
def mock_spec():
    from app.domain.types import RunnerType
    return ExperimentExecutionSpec(
        experiment_id="exp123",
        variant_id="var123",
        runner_type=RunnerType.NEBIUS,
        workload="test-workload",
        entrypoint=["python", "eval.py"],
        environment={"MODEL": "test-model"},
        resource_limits=ResourceLimits(timeout_seconds=5)
    )

@pytest.mark.asyncio
async def test_structured_metric_parsing_valid(mock_runner, mock_session, mock_run, mock_spec):
    raw_logs = '{"schema_version": "1", "status": "success", "metrics": [{"name": "quality", "value": 0.95}, {"name": "latency", "value": 150.0}]}'
    mock_runner._parse_and_store_metrics(mock_session, mock_run, raw_logs)

    assert mock_session.add.call_count == 2
    metrics = [call.args[0] for call in mock_session.add.call_args_list]
    assert metrics[0].metric_name == "quality"
    assert metrics[0].value == 0.95
    assert metrics[1].metric_name == "latency"
    assert metrics[1].value == 150.0

@pytest.mark.asyncio
async def test_structured_metric_parsing_invalid_schema(mock_runner, mock_session, mock_run, mock_spec):
    raw_logs = '{"schema_version": "2", "metrics": []}'
    with pytest.raises(ExecutionFailure) as exc:
        mock_runner._parse_and_store_metrics(mock_session, mock_run, raw_logs)

    assert exc.value.failure_type == "INVALID_OUTPUT"
    assert exc.value.stage == "PARSING"
    assert "Invalid schema version" in exc.value.message

@pytest.mark.asyncio
async def test_structured_metric_parsing_missing_metrics(mock_runner, mock_session, mock_run, mock_spec):
    raw_logs = '{"schema_version": "1", "status": "success"}'
    with pytest.raises(ExecutionFailure) as exc:
        mock_runner._parse_and_store_metrics(mock_session, mock_run, raw_logs)

    assert exc.value.failure_type == "MISSING_METRICS"

@pytest.mark.asyncio
async def test_nebius_execute_unavailable(mock_runner, mock_session, mock_run, mock_spec):
    mock_op = MagicMock()
    mock_op.id = "op123"
    mock_op.resource_id = "job123"
    async def mock_wait(): return True
    mock_op.wait = mock_wait

    mock_runner.client.create = AsyncMock(return_value=mock_op)

    mock_job = MagicMock()
    mock_job.id = "job123"
    mock_job.status.state = "DONE"
    mock_runner.client.get = AsyncMock(return_value=mock_job)

    with pytest.raises(ExecutionFailure) as exc:
        await mock_runner.execute(mock_session, mock_run, mock_spec)

    assert exc.value.failure_type == "EXECUTION_UNAVAILABLE"

@pytest.mark.asyncio
async def test_nebius_timeout(mock_runner, mock_session, mock_run, mock_spec):
    mock_op = MagicMock()
    mock_op.id = "op123"
    mock_op.resource_id = "job123"
    async def mock_wait():
        await asyncio.sleep(0.2)
        return True
    mock_op.wait = mock_wait
    mock_runner.client.create = AsyncMock(return_value=mock_op)

    # Force timeout
    mock_spec.resource_limits.timeout_seconds = 0.1

    with pytest.raises(ExecutionFailure) as exc:
        await mock_runner.execute(mock_session, mock_run, mock_spec)

    assert exc.value.failure_type == "TIMEOUT"
    assert mock_run.status == "failed"
