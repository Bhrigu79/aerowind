import pytest
import asyncio
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Project, Constraint, Experiment, ExperimentVariant, ExperimentRun, MetricResult
from app.schemas.execution import ExperimentExecutionSpec
from app.services.ai_benchmark import RealAIBenchmarkRunner
from app.gateway.gateway import ModelGateway
from app.schemas.gateway import GatewayRequest, GatewayResponse, TaskType, TokenUsage
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from app.db.models import Base

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

class MockAIGateway(ModelGateway):
    def __init__(self):
        super().__init__()

    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        self.last_request = request
        from app.core.exceptions import ProviderUnavailableError
        if getattr(request, "preferred_model", None) and request.preferred_model == "error_model":
            raise ProviderUnavailableError("nebius")

        # We need to simulate the sentiment classification task.
        # Let's just mock correct answers for everything.
        # But for Candidate (which might have different config) we can pretend it misses some.

        # Simulate latency
        await asyncio.sleep(0.01)

        # We can extract the actual text from the messages and determine ground truth to return a perfect response
        user_msg = request.messages[-1].content
        if "late and the box was completely crushed" in user_msg:
            answer = "negative"
        else:
            answer = "positive" # Just a quick mock hack for tests

        return GatewayResponse(
            content=answer,
            model="mock_model",
            provider="openai",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            latency_ms=10.0,
            request_id="req1"
        )

@pytest.mark.asyncio
async def test_real_ai_benchmark_execution(db_session: AsyncSession):
    # Setup test DB
    project = Project(
        name="AI Benchmark Project",
        description="Testing real AI benchmark",
        objective="Improve accuracy",
        target_system_description="Sentiment Classifier"
    )
    db_session.add(project)
    await db_session.flush()

    experiment = Experiment(
        project_id=project.id,
        hypothesis_id="hyp1",
        name="Test",
        experiment_type="autonomous",
        status="running",
        candidate_description="Temp 0.2"
    )
    db_session.add(experiment)

    variant = ExperimentVariant(
        project_id=project.id,
        name="Candidate",
        is_baseline=False,
        system_configuration={"temperature": 0.2, "model": "mock_model"}
    )
    db_session.add(variant)
    await db_session.flush()

    run = ExperimentRun(
        experiment_id=experiment.id,
        variant_id=variant.id,
        runner_type="ai_benchmark"
    )
    db_session.add(run)
    await db_session.commit()

    # Run Benchmark
    mock_gateway = MockAIGateway()
    runner = RealAIBenchmarkRunner(gateway=mock_gateway)

    completed_run = await runner.execute(
        session=db_session,
        run=run,
        spec=None,
        metrics_to_measure=["quality_score", "p95_latency_ms", "error_rate", "cost_per_request_usd"]
    )

    assert completed_run.success is True
    assert completed_run.status == "completed"

    # Verify Metrics
    from sqlalchemy import select
    stmt = select(MetricResult).where(MetricResult.run_id == completed_run.id)
    metrics = (await db_session.execute(stmt)).scalars().all()

    assert len(metrics) == 4
    metric_dict = {m.metric_name: m.value for m in metrics}

    assert "quality_score" in metric_dict
    assert "p95_latency_ms" in metric_dict
    assert "error_rate" in metric_dict
    assert "cost_per_request_usd" in metric_dict

    # Since we mocked the answer mostly to "positive" and only one "negative" based on text check,
    # the accuracy will be calculated exactly. We don't need to assert exact number, just > 0.
    assert metric_dict["quality_score"] > 0.0
    assert metric_dict["error_rate"] == 0.0

    # Assert execution metadata format
    assert completed_run.execution_metadata["schema_version"] == "1"
    assert completed_run.execution_metadata["status"] == "success"
    assert "metrics" in completed_run.execution_metadata
    assert len(completed_run.execution_metadata["metrics"]) == 4
    for m in completed_run.execution_metadata["metrics"]:
        assert "name" in m
        assert "value" in m
        assert "unit" in m
        assert "sample_size" in m

@pytest.mark.asyncio
async def test_real_ai_benchmark_provider_routing(db_session: AsyncSession):
    project = Project(name="P", objective="O", status="active")
    db_session.add(project)
    await db_session.flush()

    exp = Experiment(project_id=project.id, name="E", experiment_type="autonomous", status="planned", candidate_description="desc")
    db_session.add(exp)
    await db_session.flush()

    variant = ExperimentVariant(
        project_id=project.id,
        name="V",
        is_baseline=False,
        system_configuration={"temperature": 0.5, "model": "nvidia/llama-3.1-nemotron-70b-instruct", "provider": "nebius"}
    )
    db_session.add(variant)
    await db_session.flush()

    run = ExperimentRun(experiment_id=exp.id, variant_id=variant.id, runner_type="real_ai")
    db_session.add(run)
    await db_session.flush()

    gateway = MockAIGateway()
    runner = RealAIBenchmarkRunner(gateway)

    await runner.execute(db_session, run, metrics_to_measure=["quality"])

    assert gateway.last_request.preferred_provider == "nebius"
    assert gateway.last_request.preferred_model == "nvidia/llama-3.1-nemotron-70b-instruct"

@pytest.mark.asyncio
async def test_real_ai_benchmark_propagates_provider_error(db_session: AsyncSession):
    project = Project(name="P2", objective="O2", status="active")
    db_session.add(project)
    await db_session.flush()

    exp = Experiment(project_id=project.id, name="E2", experiment_type="autonomous", status="planned", candidate_description="desc2")
    db_session.add(exp)
    await db_session.flush()

    variant = ExperimentVariant(
        project_id=project.id,
        name="V2",
        is_baseline=False,
        system_configuration={"temperature": 0.5, "model": "error_model"}
    )
    db_session.add(variant)
    await db_session.flush()

    run = ExperimentRun(experiment_id=exp.id, variant_id=variant.id, runner_type="real_ai")
    db_session.add(run)
    await db_session.flush()

    gateway = MockAIGateway()
    runner = RealAIBenchmarkRunner(gateway)

    from app.core.exceptions import ProviderUnavailableError
    with pytest.raises(ProviderUnavailableError):
        await runner.execute(db_session, run, metrics_to_measure=["quality"])
