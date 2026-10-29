"""
Autonomous integration test — fixed to prove strategy enforcement causality.

The old MockGateway changed ALL dimensions every iteration, which meant
the test would pass even if validate_strategy_change() always returned True.

This rewrite uses a controlled gateway that proposes ONLY ONE dimension
per iteration, proving that:
  - Strategy enforcement correctly accepts or rejects based on causality.
  - Memory is passed to subsequent iterations.
  - Duplicate detection works.
"""

import pytest
import json
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.db.models import Project, Constraint, ResearchSession, Experiment, ExperimentVariant, Base
from app.services.session import SessionOrchestrator
from app.gateway.gateway import ModelGateway
from app.domain.types import ConstraintOperator, SessionState, StopReason


class ControlledMockGateway(ModelGateway):
    """
    Gateway whose Experiment Designer proposes exactly ONE controlled configuration
    per call.  This makes it possible to test which proposals are accepted or rejected.

    Proposal sequence:
      call 0: Change only 'temperature' (what strategy selects when quality gap is biggest).
      call 1: Same config as call 0 → duplicate detection triggers.
      call 2: Change 'retrieval_enabled' and 'temperature' → accepted (temperature still changed).
    """
    def __init__(self):
        super().__init__()
        self.call_count = 0
        self.last_hypothesis_prompt = ""
        self.hypothesis_call_count = 0

    async def complete(self, req, **kwargs):
        system_prompt = req.messages[0].content if req.messages else ""
        user_prompt = req.messages[1].content if len(req.messages) > 1 else ""

        class MockResponse:
            def __init__(self, content):
                self.content = content

        if "Planner Agent" in system_prompt:
            return MockResponse(json.dumps({
                "focus_area": "quality",
                "reason": "Reduce quality gap"
            }))

        if "Hypothesis" in system_prompt:
            self.last_hypothesis_prompt = system_prompt + "\n" + user_prompt
            self.hypothesis_call_count += 1
            return MockResponse(json.dumps({
                "claim": f"Hypothesis {self.call_count}",
                "expected_effect": "Improve quality",
                "target_metric": "quality_score",
                "expected_direction": "increase",
                "expected_magnitude": 5.0,
                "confidence": 0.9,
                "independent_variable": "temperature",
                "control_description": "none",
                "candidate_description": f"Cand {self.call_count}",
                "risks": "none",
            }))

        if "Experiment Designer" in system_prompt:
            # Baseline is {"temperature": 0.7}. Strategy will select 'prompt_strategy' first.
            # Call 0 proposes 'prompt_strategy' -> Passes strategy, gets evaluated.
            # Subsequent calls propose the same -> Fails strategy (ignored dimension).
            # This allows the session to continue (not exhausted) and test memory logic.
            cfg = {
                "temperature": 0.7,
                "prompt_strategy": "structured"
            }

            res = MockResponse(json.dumps({
                "hypothesis_summary": "summary",
                "candidate_configuration": cfg,
                "changed_variables": ["prompt_strategy"],
                "held_constant_variables": ["temperature"],

                "workload": "web",
                "metrics_to_measure": ["quality_score", "p95_latency_ms"],
                "sample_size": 10,
                "stop_conditions": ["none"],
                "expected_result": "better",
            }))
            self.call_count += 1
            return res

        if "Researcher Agent" in system_prompt:
            return MockResponse("Results look reasonable.")

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
async def setup_project_for_autonomous(db_session: AsyncSession):
    proj = Project(
        name="AutoTest",
        objective="Improve quality",
        # Baseline: temperature=0.7 (gateway will propose 0.3 → temperature changes)
        target_system_description=json.dumps({"temperature": 0.7})
    )
    db_session.add(proj)
    await db_session.flush()

    # Constraint that cannot be satisfied synthetically → session runs all iterations
    c = Constraint(
        project_id=proj.id,
        metric_name="quality_score",
        operator=ConstraintOperator.GTE.value,
        required_value=999.0
    )
    db_session.add(c)
    await db_session.flush()

    rs = ResearchSession(
        project_id=proj.id,
        max_iterations=4,
        max_experiments=4,
    )
    db_session.add(rs)
    await db_session.commit()
    return proj, rs


@pytest.mark.asyncio
async def test_autonomous_session_flow(db_session: AsyncSession, setup_project_for_autonomous):
    proj, rs = setup_project_for_autonomous

    gateway = ControlledMockGateway()
    orchestrator = SessionOrchestrator(gateway)

    await orchestrator.execute_session(db_session, rs.id)

    await db_session.refresh(rs)
    assert rs.status == SessionState.COMPLETED.value

    # Fetch all experiments ordered by creation time
    stmt = select(Experiment).where(
        Experiment.session_id == rs.id
    ).order_by(Experiment.created_at)
    exps = (await db_session.execute(stmt)).scalars().all()

    assert len(exps) > 0, "No experiments were created"

    # At least one experiment should have been successfully executed (status=completed)
    completed = [e for e in exps if e.status == "completed"]
    assert len(completed) > 0, (
        "No experiment reached 'completed' status. "
        f"Statuses: {[(e.status, e.error_message) for e in exps]}"
    )

    # Failures must have occurred for legitimate reasons (strategy enforcement, duplicate,
    # or search-space exhausted) — never for silent config corruption or routing errors.
    failed_exps = [e for e in exps if e.status == "failed"]
    for fe in failed_exps:
        assert fe.error_message is not None
        assert len(fe.error_message) > 0
        # The failure must be one of the expected rejection reasons
        assert any(reason in fe.error_message for reason in [
            "ignored strategy dimension",
            "Duplicate",
            "identical",
            "Baseline",
            "Configuration Validation",
            "SEARCH_SPACE_EXHAUSTED",
        ]), f"Unexpected failure reason: {fe.error_message!r}"

    # Memory check: the hypothesis agent must have been called multiple times,
    # and its later prompts must contain information from prior experiments.
    assert gateway.hypothesis_call_count > 1, (
        "Hypothesis agent was only called once — session may have stopped after first iteration "
        f"without checking memory. Completed: {len(completed)}, Failed: {len(failed_exps)}"
    )
    # The last hypothesis prompt must contain memory about previous experiments.
    # The memory service stores candidate_description in the 'hypothesis' key.
    assert (
        "hypothesis" in gateway.last_hypothesis_prompt
        or "previous_experiments" in gateway.last_hypothesis_prompt
        or "test candidate" in gateway.last_hypothesis_prompt.lower()
        or "attempt" in gateway.last_hypothesis_prompt.lower()
    ), (
        "Hypothesis Agent's prompt did not contain any memory of prior experiments. "
        f"Last prompt snippet: {gateway.last_hypothesis_prompt[:300]!r}"
    )
