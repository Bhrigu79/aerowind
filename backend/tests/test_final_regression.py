import pytest
import json
from unittest.mock import patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import (
    Project, Constraint, ExperimentVariant, Experiment,
    ResearchSession, ExperimentRun, MetricResult, ExperimentPlan
)
from app.gateway.adapters.nebius import NebiusAdapter
from app.schemas.gateway import GatewayRequest, TaskType, Provider, GatewayResponse, TokenUsage
from app.services.orchestrator import ResearchOrchestrator
from app.gateway.gateway import ModelGateway
from app.services.memory import ResearchMemoryService
from app.services.certificate import CertificateService
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

class MockResponse:
    def __init__(self, content):
        self.content = content

class FixedConfigGateway(ModelGateway):
    def __init__(self, candidate_config: dict):
        super().__init__()
        self.candidate_config = candidate_config

    async def complete(self, req, **kwargs):
        sys = req.messages[0].content if req.messages else ""
        if "Hypothesis" in sys:
            return MockResponse(json.dumps({
                "claim": "Test claim",
                "expected_effect": "Improve quality",
                "target_metric": "quality_score",
                "expected_direction": "increase",
                "expected_magnitude": 5.0,
                "confidence": 0.8,
                "independent_variable": "temperature",
                "control_description": "default",
                "candidate_description": "test candidate",
                "risks": "none",
            }))
        if "Experiment Designer" in sys:
            return MockResponse(json.dumps({
                "hypothesis_summary": "summary",
                "candidate_configuration": self.candidate_config,
                "changed_variables": list(self.candidate_config.keys()),
                "held_constant_variables": [],
                "workload": "synthetic",
                "metrics_to_measure": ["quality_score"],
                "sample_size": 100,
                "stop_conditions": [],
                "expected_result": "improvement",
            }))
        return MockResponse("{}")


@pytest.mark.asyncio
async def test_regression_model_provenance(db_session: AsyncSession):
    # 1. requested model cannot silently differ from actual model without provenance
    from app.services.ai_benchmark import RealAIBenchmarkRunner
    gw = ModelGateway()
    runner = RealAIBenchmarkRunner(gw)

    mock_resp = GatewayResponse(
        content="positive",
        provider=Provider.NEBIUS,
        model="actual_model_returned",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20, is_missing=False, known_cost_usd=0.01),
        latency_ms=100.0,
        request_id="123",
        finish_reason="stop"
    )
    gw.complete = AsyncMock(return_value=mock_resp)

    run = ExperimentRun(
        id="run_123",
        experiment_id="exp_123",
        variant_id="var_123",
        status="pending",
        runner_type="real_ai",
        execution_provenance="REAL_EXECUTION",
    )
    v = ExperimentVariant(
        id="var_123",
        project_id="proj_1",
        name="var_name",
        is_baseline=False,
        system_configuration={"model": "requested_model", "temperature": 0.1, "sample_count": 1}
    )
    db_session.add(v)
    await db_session.commit()

    # We must patch get() so that the runner can fetch the variant correctly
    db_session.get = AsyncMock(return_value=v)

    await runner.execute(db_session, run)

    assert run.execution_metadata["model"] == "actual_model_returned"
    assert run.execution_metadata["requested_model"] == "requested_model"
    assert run.execution_metadata["model_mismatch"] is True


@pytest.mark.asyncio
async def test_regression_fallback_prevention():
    # 2. provider fallback cannot happen in controlled real execution
    # This is validated by checking ai_benchmark uses allow_fallback=False
    from app.services.ai_benchmark import RealAIBenchmarkRunner
    gw = ModelGateway()
    runner = RealAIBenchmarkRunner(gw)

    gw.complete = AsyncMock()
    v = ExperimentVariant(
        id="var_124",
        system_configuration={"model": "nebius", "sample_count": 1}
    )
    run = ExperimentRun(id="run_124", variant_id="var_124")

    mock_session = AsyncMock()
    mock_session.get.return_value = v

    try:
        await runner.execute(mock_session, run)
    except Exception:
        pass

    call_args = gw.complete.call_args[0][0]
    assert call_args.allow_fallback is False


@pytest.mark.asyncio
async def test_regression_missing_model_output_fails():
    # 3. missing model output cannot become a successful metric
    adapter = NebiusAdapter()
    req = GatewayRequest(task_type=TaskType.CLASSIFICATION, messages=[])

    class MockResp:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": ""}}], "usage": {}}

    with patch.object(adapter, '_get_client') as mock_client:
        mock_client.return_value.post = AsyncMock(return_value=MockResp())
        with pytest.raises(Exception) as exc:
            await adapter.complete(req)
        assert "empty or missing content" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_regression_synthetic_metrics_for_real(db_session: AsyncSession):
    # 4. real execution cannot use synthetic benchmark metrics
    # MetricResult.source must be 'real_ai_benchmark_v1'
    from app.services.ai_benchmark import RealAIBenchmarkRunner
    gw = ModelGateway()
    runner = RealAIBenchmarkRunner(gw)
    mock_resp = GatewayResponse(
        content="positive", provider=Provider.NEBIUS, model="x",
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2, is_missing=False, known_cost_usd=None),
        latency_ms=10, request_id="1", finish_reason="stop"
    )
    gw.complete = AsyncMock(return_value=mock_resp)

    v = ExperimentVariant(id="var_125", project_id="proj_1", name="name", is_baseline=False, system_configuration={"model": "x", "sample_count": 1})
    run = ExperimentRun(id="run_125", experiment_id="exp_125", variant_id="var_125", runner_type="real_ai")

    db_session.add(v)
    db_session.add(run)
    await db_session.commit()

    await runner.execute(db_session, run)

    metrics = (await db_session.execute(select(MetricResult).where(MetricResult.run_id == run.id))).scalars().all()
    for m in metrics:
        assert m.source == "real_ai_benchmark_v1"
        assert m.source != "synthetic"


@pytest.mark.asyncio
async def test_regression_holdout_memory(db_session: AsyncSession):
    # 5. holdout evidence cannot enter optimization memory
    proj = Project(name="P", objective="O")
    db_session.add(proj)
    await db_session.flush()

    exp_holdout = Experiment(
        project_id=proj.id,
        name="Holdout",
        experiment_type="holdout_validation",
        status="completed",
        adopted=True,
        candidate_description="holdout description"
    )
    db_session.add(exp_holdout)

    exp_opt = Experiment(
        project_id=proj.id,
        name="Optimization",
        experiment_type="autonomous",
        status="completed",
        adopted=True,
        candidate_description="optimization description"
    )
    db_session.add(exp_opt)

    # We must add plan and baseline variants to satisfy the relationships
    v_base = ExperimentVariant(project_id=proj.id, name="base", is_baseline=True)
    v_cand = ExperimentVariant(project_id=proj.id, name="cand", is_baseline=False)
    db_session.add_all([v_base, v_cand])
    await db_session.flush()

    plan1 = ExperimentPlan(experiment_id=exp_holdout.id, baseline_variant_id=v_base.id, candidate_variant_id=v_cand.id, hypothesis_summary="", workload="")
    plan2 = ExperimentPlan(experiment_id=exp_opt.id, baseline_variant_id=v_base.id, candidate_variant_id=v_cand.id, hypothesis_summary="", workload="")
    db_session.add_all([plan1, plan2])

    await db_session.commit()

    mem = await ResearchMemoryService.get_project_memory(db_session, proj.id)
    exp_names = [e["name"] for e in mem["previous_experiments"]]

    assert "Holdout" not in exp_names
    assert "Optimization" in exp_names


@pytest.mark.asyncio
async def test_regression_certificate_global_optimum():
    # 7. certificate is derived only from persisted evidence &
    # 10. no global-optimum wording exists in judge-facing output
    import inspect
    import ast
    import textwrap
    source = inspect.getsource(CertificateService.generate_certificate)
    source = textwrap.dedent(source)

    # Strip string literals (docstrings) from the AST before checking
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            node.value.value = ""
    source_lower = ast.unparse(tree).lower()

    assert "globally optimal" not in source_lower
    assert "best possible" not in source_lower
    assert "best retained configuration under the evaluated objective constraints and research policy" in source_lower
