import pytest
import json
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.db.models import Project, Constraint, ResearchSession, Experiment, ExperimentRun, MetricResult, Base, ExperimentVariant
from app.services.orchestrator import ResearchOrchestrator
from app.gateway.gateway import ModelGateway
from app.domain.types import ConstraintOperator
from app.schemas.experiment import ExperimentCreate, ExperimentType

class MockResponse:
    def __init__(self, content):
        self.content = content

class BaseAdversarialMockGateway(ModelGateway):
    def __init__(self, proposals: list[dict]):
        super().__init__()
        self.call_count = 0
        self.proposals = proposals

    async def complete(self, req, **kwargs):
        system_prompt = req.messages[0].content if req.messages else ""

        if "Planner Agent" in system_prompt:
            return MockResponse(json.dumps({"focus_area": "test", "reason": "test"}))

        if "Hypothesis" in system_prompt:
            return MockResponse(json.dumps({
                "claim": "Test claim",
                "expected_effect": "Improve",
                "target_metric": "quality",
                "expected_direction": "increase",
                "expected_magnitude": 10.0,
                "confidence": 0.9,
                "independent_variable": "test",
                "control_description": "none",
                "candidate_description": "test cand",
                "risks": "none"
            }))

        if "Experiment Designer" in system_prompt:
            cfg = self.proposals[min(self.call_count, len(self.proposals) - 1)]
            res = MockResponse(json.dumps({
                "hypothesis_summary": "sum",
                "candidate_configuration": cfg,
                "changed_variables": list(cfg.keys()),
                "held_constant_variables": ["other"],
                "workload": "web",
                "metrics_to_measure": ["quality", "latency"],
                "sample_size": 100,
                "stop_conditions": ["none"],
                "expected_result": "better"
            }))
            self.call_count += 1
            return res

        if "Researcher Agent" in system_prompt:
            return MockResponse("Looks good.")

        return MockResponse("{}")

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

@pytest.fixture
async def base_project(db_session: AsyncSession):
    proj = Project(name="AutoTest", objective="Optimize", target_system_description=json.dumps({
        "temperature": 0.7,
        "retrieval_enabled": False,
        "pipeline_mode": "single"
    }))
    db_session.add(proj)
    await db_session.flush()
    return proj

@pytest.mark.asyncio
async def test_adversarial_strategy_rejects_disobedience(db_session: AsyncSession, base_project: Project):
    # Strategy will select something (e.g. prompt_strategy or temperature)
    # The baseline has retrieval_enabled=False, temperature=0.7, pipeline_mode="single"
    # We will force a scenario where we pretend a specific dimension was selected.
    # To reliably control what strategy selects, we can add a Constraint for quality
    # to force quality_dimensions.

    c = Constraint(project_id=base_project.id, metric_name="quality", operator=ConstraintOperator.GTE.value, required_value=100.0)
    db_session.add(c)
    await db_session.commit()

    # LLM proposes something where it ONLY changes temperature, but strategy picks "prompt_strategy".
    # Strategy picks unexplored quality dimensions in this order:
    # ["prompt_strategy", "few_shot_count", "retrieval_enabled", "pipeline_mode", "model", "temperature", "chain_of_thought", "max_tokens"]
    # It will pick "prompt_strategy".
    # So we disobey and change ONLY temperature — all proposals use canonical valid values.
    proposals = [
        {"temperature": 0.2, "retrieval_enabled": False, "pipeline_mode": "single"}, # Disobey attempt 1
        {"temperature": 0.3, "retrieval_enabled": False, "pipeline_mode": "single"}, # Disobey attempt 2
        {"temperature": 0.4, "retrieval_enabled": False, "pipeline_mode": "single"}  # Disobey attempt 3
    ]
    gateway = BaseAdversarialMockGateway(proposals)
    orchestrator = ResearchOrchestrator(gateway)

    exp = await orchestrator.execute_iteration(db_session, base_project.id)

    # Should fail because it ignored prompt_strategy
    assert exp.status == "failed"
    assert "LLM repeatedly ignored strategy dimension" in exp.error_message
    assert "'prompt_strategy'" in exp.error_message

@pytest.mark.asyncio
async def test_single_dimension_control(db_session: AsyncSession):
    from app.db.models import ExperimentPlan

    async def setup_project():
        proj = Project(name="AutoTest", objective="Optimize", target_system_description=json.dumps({
            "temperature": 0.7,
            "retrieval_enabled": False,
            "pipeline_mode": "single"
        }))
        db_session.add(proj)
        await db_session.flush()

        v_base = ExperimentVariant(project_id=proj.id, name="base", is_baseline=True, system_configuration=json.loads(proj.target_system_description))
        db_session.add(v_base)
        await db_session.flush()

        # Create completed experiments for prior dims so strategy counts them
        prior_dims = ["prompt_strategy", "few_shot_count", "retrieval_enabled", "pipeline_mode", "model"]
        for d in prior_dims:
            v = ExperimentVariant(project_id=proj.id, name=f"var_{d}", is_baseline=False, system_configuration={d: "explored"})
            db_session.add(v)
            await db_session.flush()
            exp_done = Experiment(
                project_id=proj.id, name=f"exp_{d}",
                experiment_type="autonomous", status="completed",
                adopted=False, candidate_description="",
            )
            db_session.add(exp_done)
            await db_session.flush()
            plan = ExperimentPlan(
                experiment_id=exp_done.id, hypothesis_summary="prior",
                baseline_variant_id=v_base.id, candidate_variant_id=v.id,
                changed_variables=[d], held_constant_variables=[],
                workload="synthetic", metrics_to_measure=["quality_score"],
                sample_size=100, stop_conditions=[],
            )
            db_session.add(plan)

        c = Constraint(project_id=proj.id, metric_name="quality", operator=ConstraintOperator.GTE.value, required_value=100.0)
        db_session.add(c)
        await db_session.commit()
        return proj

    # Strategy should now pick "temperature" because it's the next unexplored quality dimension.

    # Case 1: Changes only temperature -> ACCEPT
    proj1 = await setup_project()
    gw1 = BaseAdversarialMockGateway([
        {"temperature": 0.2, "retrieval_enabled": False, "pipeline_mode": "single"}
    ])
    orch1 = ResearchOrchestrator(gw1)
    exp1 = await orch1.execute_iteration(db_session, proj1.id)
    assert exp1.status != "failed"

    # Case 2: Changes only retrieval_enabled -> REJECT
    proj2 = await setup_project()
    gw2 = BaseAdversarialMockGateway([
        {"temperature": 0.7, "retrieval_enabled": True, "pipeline_mode": "single"},
        {"temperature": 0.7, "retrieval_enabled": True, "pipeline_mode": "single"},
        {"temperature": 0.7, "retrieval_enabled": True, "pipeline_mode": "single"}
    ])
    orch2 = ResearchOrchestrator(gw2)
    exp2 = await orch2.execute_iteration(db_session, proj2.id)
    assert exp2.status == "failed"
    assert "temperature" in exp2.error_message

    # Case 3: Changes temperature + retrieval_enabled -> ACCEPT
    proj3 = await setup_project()
    gw3 = BaseAdversarialMockGateway([
        {"temperature": 0.2, "retrieval_enabled": True, "pipeline_mode": "single"}
    ])
    orch3 = ResearchOrchestrator(gw3)
    exp3 = await orch3.execute_iteration(db_session, proj3.id)
    assert exp3.status != "failed"


@pytest.mark.asyncio
async def test_dynamic_strategy_selection(db_session: AsyncSession):
    # Scenario A: quality is largest gap -> picks quality dimension
    proj_a = Project(name="ProjA", objective="", target_system_description="{}")
    db_session.add(proj_a)
    await db_session.flush()
    c_q = Constraint(project_id=proj_a.id, metric_name="quality", operator=ConstraintOperator.GTE.value, required_value=100.0)
    c_l = Constraint(project_id=proj_a.id, metric_name="latency", operator=ConstraintOperator.LTE.value, required_value=10.0)
    db_session.add(c_q)
    db_session.add(c_l)

    # Mock metrics where quality gap is 1.0 (0/100) and latency gap is 0 (pass)
    run_a = ExperimentRun(experiment_id="fake", variant_id="fake", runner_type="synthetic")
    db_session.add(run_a)
    await db_session.flush()
    m1 = MetricResult(run_id=run_a.id, metric_name="quality", value=0.0, unit="", direction="higher_is_better", sample_size=100, source="synthetic")
    m2 = MetricResult(run_id=run_a.id, metric_name="latency", value=5.0, unit="", direction="lower_is_better", sample_size=100, source="synthetic")
    db_session.add(m1)
    db_session.add(m2)

    # Create an adopted experiment with this run so it becomes baseline metrics
    v_base = ExperimentVariant(project_id=proj_a.id, name="base", is_baseline=True, system_configuration={})
    db_session.add(v_base)
    await db_session.flush()
    run_a.variant_id = v_base.id
    exp_a = Experiment(project_id=proj_a.id, name="base", status="completed", experiment_type="baseline", adopted=True, candidate_description="")
    db_session.add(exp_a)
    await db_session.flush()
    run_a.experiment_id = exp_a.id
    await db_session.commit()

    # Try orchestrator A
    # Largest gap is quality. Strategy should pick "prompt_strategy".
    # LLM proposes change in latency dimension (max_tokens). Should be rejected.
    gw_a = BaseAdversarialMockGateway([
        {"max_tokens": 1024}
    ] * 3)
    orch_a = ResearchOrchestrator(gw_a)
    exp_res_a = await orch_a.execute_iteration(db_session, proj_a.id)
    assert exp_res_a.status == "failed"
    assert "prompt_strategy" in exp_res_a.error_message
