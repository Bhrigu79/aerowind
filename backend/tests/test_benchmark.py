import pytest
import json
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.db.models import Project, Constraint, ResearchSession, Experiment, ExperimentRun, MetricResult, Base
from app.services.session import SessionOrchestrator
from app.services.runner import SyntheticExperimentRunner
from app.services.progress import ObjectiveProgressService
from app.gateway.gateway import ModelGateway
from app.domain.types import ConstraintOperator

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    async with async_session() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def benchmark_project(db_session: AsyncSession):
    proj = Project(
        name="Customer Support Benchmark",
        objective="Optimize support answering system",
        target_system_description="Support AI"
    )
    db_session.add(proj)
    await db_session.flush()

    constraints = [
        Constraint(project_id=proj.id, metric_name="quality_score", operator=ConstraintOperator.GTE.value, required_value=92.0),
        Constraint(project_id=proj.id, metric_name="p95_latency_ms", operator=ConstraintOperator.LTE.value, required_value=2000.0),
        Constraint(project_id=proj.id, metric_name="cost_per_request_usd", operator=ConstraintOperator.LTE.value, required_value=0.03)
    ]
    db_session.add_all(constraints)
    await db_session.commit()

    return proj

@pytest.fixture
async def synthetic_runner():
    return SyntheticExperimentRunner()

# Helper to run a config and get metrics directly (Tests A, B, D, E, F)
async def run_config(config: dict, runner, db_session, project_id):
    # Setup dummy experiment run
    from app.db.models import ExperimentVariant
    exp = Experiment(
        project_id=project_id,
        name="Test",
        experiment_type="synthetic",
        candidate_description="Test candidate",
        status="pending"
    )
    db_session.add(exp)
    await db_session.flush()

    var = ExperimentVariant(project_id=project_id, name="Candidate", system_configuration=config, is_baseline=False)
    db_session.add(var)
    await db_session.flush()

    run = ExperimentRun(experiment_id=exp.id, variant_id=var.id, runner_type="synthetic", status="pending")
    db_session.add(run)
    await db_session.flush()

    await runner.execute(db_session, run, metrics_to_measure=["quality_score", "p95_latency_ms", "cost_per_request_usd"])
    await db_session.flush()

    stmt = select(MetricResult).where(MetricResult.run_id == run.id)
    metrics = (await db_session.execute(stmt)).scalars().all()

    return {m.metric_name: m.value for m in metrics}

@pytest.mark.asyncio
async def test_baseline_fails(benchmark_project, synthetic_runner, db_session):
    """A. The initial baseline does NOT satisfy the objective."""
    config = {"temperature": 0.7, "model": "8b"}
    metrics = await run_config(config, synthetic_runner, db_session, benchmark_project.id)
    assert metrics["quality_score"] < 92.0

@pytest.mark.asyncio
async def test_tradeoffs(benchmark_project, synthetic_runner, db_session):
    """
    B, D, E, F:
    Multiple dimensions improve different constraints.
    Changing one can worsen another.
    """
    baseline = {"model": "nemotron-8b", "retrieval_enabled": False, "chain_of_thought": False, "prompt_strategy": "direct", "few_shot_count": 0}
    m_base = await run_config(baseline, synthetic_runner, db_session, benchmark_project.id)

    # Enable retrieval: should increase quality but increase latency/cost
    retrieval_cfg = {**baseline, "retrieval_enabled": True}
    m_ret = await run_config(retrieval_cfg, synthetic_runner, db_session, benchmark_project.id)

    assert m_ret["quality_score"] > m_base["quality_score"]
    assert m_ret["cost_per_request_usd"] > m_base["cost_per_request_usd"]
    assert m_ret["cost_per_request_usd"] > m_base["cost_per_request_usd"]

    # 70b model vs 8b model: much higher quality, but higher cost
    large_cfg = {**baseline, "model": "nemotron-70b"}
    m_large = await run_config(large_cfg, synthetic_runner, db_session, benchmark_project.id)

    assert m_large["quality_score"] > m_base["quality_score"]
    assert m_large["cost_per_request_usd"] > m_base["cost_per_request_usd"]

    # F: A configuration that improves latency can be rejected because quality is insufficient.
    # We test just the metric part here. 8b model has good latency but poor quality.
    assert m_base["p95_latency_ms"] <= 2000.0  # Or close to it, wait actual base latency for 8b might be around 1400.
    assert m_base["quality_score"] < 92.0


class BenchmarkMockGateway(ModelGateway):
    """
    Mock LLM that acts deterministically based on the strategy prompt.
    Tests C, G, H, I, J, K, L.
    """
    def __init__(self):
        super().__init__()
        self.call_count = 0
        self.proposals = [
            {"temperature": 0.7, "retrieval_enabled": True},
            {"temperature": 0.7, "retrieval_enabled": True, "chain_of_thought": True},
            {"temperature": 0.7, "retrieval_enabled": True, "chain_of_thought": True, "prompt_strategy": "structured"},
            {"temperature": 0.7, "retrieval_enabled": True, "chain_of_thought": True, "prompt_strategy": "structured", "few_shot_count": 3},
            # Backup
            {"max_tokens": 100}
        ]

    async def complete(self, req, **kwargs):
        sys_prompt = req.messages[0].content
        user_prompt = req.messages[1].content if len(req.messages) > 1 else ""

        class MockResponse:
            def __init__(self, content):
                self.content = content

        if "Planner Agent" in sys_prompt:
            return MockResponse(json.dumps({"focus_area": "test", "reason": "test reason"}))

        if "Hypothesis" in sys_prompt:
            import re
            m = re.search(r"optimizing the dimension: '([^']+)'", user_prompt)
            dim = m.group(1) if m else "retrieval_enabled"
            return MockResponse(json.dumps({
                "claim": "Test claim",
                "expected_effect": "Improve",
                "target_metric": "quality_score",
                "expected_direction": "increase",
                "expected_magnitude": 5.0,
                "confidence": 0.9,
                "independent_variable": dim,
                "control_description": "none",
                "candidate_description": "Cand",
                "risks": "none",
            }))

        if "Experiment Designer" in sys_prompt:
            import re
            m = re.search(r'"independent_variable":\s*"([^"]+)"', user_prompt)
            dim = m.group(1) if m else "retrieval_enabled"

            # Follow the script
            if self.call_count < len(self.proposals):
                cfg = self.proposals[self.call_count]
                # Ensure the requested dimension is in the changed variables
                if dim not in cfg:
                    cfg[dim] = True # Force it so strategy validates

                res = MockResponse(json.dumps({
                    "hypothesis_summary": "summary",
                    "candidate_configuration": cfg,
                    "changed_variables": [dim],
                    "held_constant_variables": [],
                    "workload": "web",
                    "metrics_to_measure": ["quality_score", "p95_latency_ms", "cost_per_request_usd"],
                    "sample_size": 10,
                    "stop_conditions": ["none"],
                    "expected_result": "better"
                }))
                self.call_count += 1
                return res

            # Fallback for search exhaustion: provide a valid non-baseline value
            cfg = {"model": "nemotron-8b"}
            if dim == "model": cfg[dim] = "nemotron-70b"
            elif dim == "temperature": cfg[dim] = 0.5
            elif dim == "max_tokens": cfg[dim] = 2000
            elif dim == "prompt_strategy": cfg[dim] = "structured"
            elif dim == "few_shot_count": cfg[dim] = 5
            elif dim == "retrieval_enabled": cfg[dim] = True
            elif dim == "pipeline_mode": cfg[dim] = "draft_critique"
            elif dim == "chain_of_thought": cfg[dim] = True

            return MockResponse(json.dumps({
                "hypothesis_summary": "summary",
                "candidate_configuration": cfg,
                "changed_variables": [dim],
                "held_constant_variables": [],
                "workload": "web",
                "metrics_to_measure": ["quality_score", "p95_latency_ms", "cost_per_request_usd"],
                "sample_size": 10,
                "stop_conditions": ["none"],
                "expected_result": "better"
            }))

        if "Researcher Agent" in sys_prompt:
            return MockResponse("Reasonable.")

        return MockResponse("{}")


@pytest.mark.asyncio
async def test_autonomous_benchmark_loop(benchmark_project, db_session):
    """
    Tests C, G, H, I, J.
    Runs the full loop using BenchmarkMockGateway.
    """
    gateway = BenchmarkMockGateway()
    runner = SyntheticExperimentRunner()
    orchestrator = SessionOrchestrator(gateway, runner)

    rs = ResearchSession(project_id=benchmark_project.id, max_iterations=5, status="running")
    db_session.add(rs)
    await db_session.flush()

    await orchestrator.execute_session(db_session, rs.id)

    # Reload session
    await db_session.refresh(rs)

    # It should have successfully found the winning configuration and satisfied the objective
    assert rs.status == "completed"

    # Verify we ran multiple experiments (C)
    assert rs.iteration_count > 1

    # Verify objective satisfaction caused completion (J)
    assert rs.termination_reason == "OBJECTIVE_SATISFIED"

@pytest.mark.asyncio
async def test_search_exhaustion(benchmark_project, db_session):
    """
    Test K, L: Search exhaustion.
    If we set an impossible objective, it explores everything and exits cleanly.
    """
    # Make objective impossible
    stmt = select(Constraint).where(Constraint.project_id == benchmark_project.id)
    constraints = (await db_session.execute(stmt)).scalars().all()
    for c in constraints:
        if c.metric_name == "quality_score":
            c.required_value = 100.0 # Impossible
    await db_session.commit()

    gateway = BenchmarkMockGateway()
    runner = SyntheticExperimentRunner()
    orchestrator = SessionOrchestrator(gateway, runner)

    rs = ResearchSession(project_id=benchmark_project.id, max_iterations=50, max_experiments=50, status="running")
    db_session.add(rs)
    await db_session.flush()

    await orchestrator.execute_session(db_session, rs.id)
    await db_session.refresh(rs)

    stmt = select(Experiment).where(Experiment.project_id == benchmark_project.id)
    exps = (await db_session.execute(stmt)).scalars().all()
    for e in exps:
        print(f"EXP: {e.name}, status={e.status}, err={e.error_message}")

    assert rs.status == "completed"
    assert rs.termination_reason == "SEARCH_SPACE_EXHAUSTED"
