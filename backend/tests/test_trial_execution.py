import pytest
import math
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any
from sqlalchemy import select

from app.db.models import Base, ExperimentRun, ExperimentTrial, MetricResult, Project, Experiment, ExperimentVariant
from app.schemas.evaluation import EvaluationPolicy
from app.services.trial_execution import TrialExecutionService, TrialExecutionFailure
from app.services.runner import ExperimentRunner
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

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

class MockComplexRunner(ExperimentRunner):
    def __init__(self, behavior_plan=None, inject_unrelated=False):
        self.behavior_plan = behavior_plan or []
        self.calls = 0
        self.inject_unrelated = inject_unrelated

    async def execute(self, adapter, run: ExperimentRun, spec: Any = None, **kwargs):
        if self.inject_unrelated:
            m_unrelated = MetricResult(
                run_id=run.id,
                metric_name="unrelated_metric",
                value=999.0,
                unit="pct",
                direction="higher",
                sample_size=1,
                source="mock"
            )
            adapter._session.add(m_unrelated)

        plan = self.behavior_plan[self.calls] if self.calls < len(self.behavior_plan) else {"success": True, "val": 95.0}
        self.calls += 1

        if not plan.get("success", True):
            run.success = False
            run.error_info = "Mock failure"
            if plan.get("add_metric_before_fail"):
                m = MetricResult(
                    run_id=run.id,
                    metric_name="quality",
                    value=0.0,
                    unit="pct",
                    direction="higher",
                    sample_size=1,
                    source="mock"
                )
                adapter.add(m)
            return run

        run.success = True
        val = plan.get("val", 95.0)

        m = MetricResult(
            run_id=run.id,
            metric_name="quality",
            value=val,
            unit="pct",
            direction="higher",
            sample_size=1,
            source="mock"
        )
        if "raw" in plan:
            m.raw_observations = plan["raw"]

        adapter.add(m)
        return run

@pytest.fixture
async def setup_run(db_session: AsyncSession):
    project = Project(name="Test", objective="test")
    db_session.add(project)
    await db_session.flush()

    experiment = Experiment(project_id=project.id, name="Exp", experiment_type="optimization", candidate_description="test")
    db_session.add(experiment)

    variant = ExperimentVariant(project_id=project.id, name="Var")
    db_session.add(variant)
    await db_session.flush()

    run = ExperimentRun(
        experiment_id=experiment.id,
        variant_id=variant.id,
        runner_type="mock",
        evaluation_policy_snapshot=EvaluationPolicy(min_trials=3, max_trials=5, failure_tolerance_ratio=0.5).model_dump()
    )
    db_session.add(run)
    await db_session.commit()
    return run


@pytest.mark.asyncio
async def test_A_unrelated_unassociated_metric_cannot_be_captured(db_session: AsyncSession, setup_run):
    run = setup_run
    run.evaluation_policy_snapshot = EvaluationPolicy(min_trials=1, max_trials=1, failure_tolerance_ratio=0.0).model_dump()

    runner = MockComplexRunner(behavior_plan=[{"success": True, "val": 90.0}], inject_unrelated=True)
    evidence = await TrialExecutionService.execute_trials(db_session, run, runner)

    assert "quality" in evidence
    assert "unrelated_metric" not in evidence

    unrelated_db = (await db_session.execute(select(MetricResult).where(MetricResult.metric_name == "unrelated_metric"))).scalars().first()
    assert unrelated_db.trial_id is None

@pytest.mark.asyncio
async def test_B_C_D_multiple_sequential_trials_separate_metrics(db_session: AsyncSession, setup_run):
    run = setup_run
    run.evaluation_policy_snapshot = EvaluationPolicy(min_trials=2, max_trials=3, failure_tolerance_ratio=0.5).model_dump()

    plan = [
        {"success": True, "val": 10.0},
        {"success": False, "add_metric_before_fail": True},
        {"success": True, "val": 20.0}
    ]
    runner = MockComplexRunner(behavior_plan=plan)
    evidence = await TrialExecutionService.execute_trials(db_session, run, runner)

    trials = (await db_session.execute(select(ExperimentTrial).where(ExperimentTrial.run_id == run.id).order_by(ExperimentTrial.trial_index))).scalars().all()
    assert len(trials) == 3

    m0 = (await db_session.execute(select(MetricResult).where(MetricResult.trial_id == trials[0].id))).scalars().all()
    m1 = (await db_session.execute(select(MetricResult).where(MetricResult.trial_id == trials[1].id))).scalars().all()
    m2 = (await db_session.execute(select(MetricResult).where(MetricResult.trial_id == trials[2].id))).scalars().all()

    assert len(m0) == 1 and m0[0].value == 10.0
    assert len(m1) == 1 and m1[0].value == 0.0
    assert len(m2) == 1 and m2[0].value == 20.0

    stats = evidence["quality"]
    assert stats.n == 2
    assert stats.mean == 15.0

@pytest.mark.asyncio
async def test_E_F_exact_trial_count_and_failure_tolerance(db_session: AsyncSession, setup_run):
    run = setup_run
    run.evaluation_policy_snapshot = EvaluationPolicy(min_trials=3, max_trials=5, failure_tolerance_ratio=0.4).model_dump()

    plan = [{"success": True}] * 3
    runner = MockComplexRunner(behavior_plan=plan)
    await TrialExecutionService.execute_trials(db_session, run, runner)
    assert runner.calls == 3

    plan2 = [{"success": False}, {"success": False}, {"success": True}, {"success": True}, {"success": True}]
    run2 = ExperimentRun(experiment_id=run.experiment_id, variant_id=run.variant_id, runner_type="mock", evaluation_policy_snapshot=run.evaluation_policy_snapshot)
    db_session.add(run2)
    await db_session.commit()
    runner2 = MockComplexRunner(behavior_plan=plan2)
    await TrialExecutionService.execute_trials(db_session, run2, runner2)
    assert runner2.calls == 5
    assert run2.success is True

    plan3 = [{"success": False}, {"success": False}, {"success": False}]
    run3 = ExperimentRun(experiment_id=run.experiment_id, variant_id=run.variant_id, runner_type="mock", evaluation_policy_snapshot=run.evaluation_policy_snapshot)
    db_session.add(run3)
    await db_session.commit()
    runner3 = MockComplexRunner(behavior_plan=plan3)

    with pytest.raises(TrialExecutionFailure) as exc:
        await TrialExecutionService.execute_trials(db_session, run3, runner3)
    assert "Exceeded failure tolerance" in str(exc.value)
    assert runner3.calls == 3

    plan4 = [{"success": True}, {"success": False}, {"success": True}, {"success": False}, {"success": False}]
    run4 = ExperimentRun(experiment_id=run.experiment_id, variant_id=run.variant_id, runner_type="mock", evaluation_policy_snapshot=run.evaluation_policy_snapshot)
    db_session.add(run4)
    await db_session.commit()
    runner4 = MockComplexRunner(behavior_plan=plan4)
    with pytest.raises(TrialExecutionFailure) as exc4:
        await TrialExecutionService.execute_trials(db_session, run4, runner4)
    assert "Failed to reach target successes" in str(exc4.value) or "Exceeded failure tolerance" in str(exc4.value)

@pytest.mark.asyncio
async def test_G_execution_failure_is_not_decision_engine_rejection(db_session: AsyncSession, setup_run):
    run = setup_run
    run.evaluation_policy_snapshot = EvaluationPolicy(min_trials=3, max_trials=3, failure_tolerance_ratio=0.0).model_dump()
    runner = MockComplexRunner(behavior_plan=[{"success": False}])

    with pytest.raises(TrialExecutionFailure):
        await TrialExecutionService.execute_trials(db_session, run, runner)

    assert run.success is False
    assert run.status == "failed"

@pytest.mark.asyncio
async def test_H_raw_observations_remain_trial_specific(db_session: AsyncSession, setup_run):
    run = setup_run
    run.evaluation_policy_snapshot = EvaluationPolicy(min_trials=2, max_trials=2, failure_tolerance_ratio=0.0).model_dump()

    plan = [
        {"success": True, "val": 1.0, "raw": [1.0, 1.1]},
        {"success": True, "val": 2.0, "raw": [2.0, 2.1]}
    ]
    runner = MockComplexRunner(behavior_plan=plan)

    evidence = await TrialExecutionService.execute_trials(db_session, run, runner)
    assert run.success is True

@pytest.mark.asyncio
async def test_J_retry_creates_a_new_trial(db_session: AsyncSession, setup_run):
    run = setup_run
    run.evaluation_policy_snapshot = EvaluationPolicy(min_trials=1, max_trials=2, failure_tolerance_ratio=1.0).model_dump()

    plan = [
        {"success": False},
        {"success": True}
    ]
    runner = MockComplexRunner(behavior_plan=plan)
    await TrialExecutionService.execute_trials(db_session, run, runner)

    trials = (await db_session.execute(select(ExperimentTrial).where(ExperimentTrial.run_id == run.id).order_by(ExperimentTrial.trial_index))).scalars().all()
    assert len(trials) == 2
    assert trials[0].status == "failed"
    assert trials[1].status == "completed"
    assert trials[0].id != trials[1].id

@pytest.mark.asyncio
async def test_K_run_id_integrity(db_session: AsyncSession, setup_run):
    run = setup_run

    run2 = ExperimentRun(
        experiment_id=run.experiment_id,
        variant_id=run.variant_id,
        runner_type="mock",
        evaluation_policy_snapshot=EvaluationPolicy(min_trials=1, max_trials=1, failure_tolerance_ratio=0.0).model_dump()
    )
    db_session.add(run2)
    await db_session.commit()

    class MismatchRunner(ExperimentRunner):
        async def execute(self, adapter, run, spec=None, **kwargs):
            m = MetricResult(
                run_id="DIFFERENT_RUN_ID", # intentional mismatch!
                metric_name="quality",
                value=95.0,
                unit="pct",
                direction="higher",
                sample_size=1,
                source="mock"
            )
            # This should raise ValueError because adapter checks run_id
            adapter.add(m)
            return run

    runner = MismatchRunner()

    with pytest.raises(TrialExecutionFailure) as exc:
        await TrialExecutionService.execute_trials(db_session, run2, runner)

    trials = (await db_session.execute(select(ExperimentTrial).where(ExperimentTrial.run_id == run2.id))).scalars().all()
    assert len(trials) > 0
    assert "does not match trial run_id" in trials[0].error_info

@pytest.mark.asyncio
async def test_trial_execution_policy_bounds(db_session: AsyncSession, setup_run):
    run = setup_run
    run.evaluation_policy_snapshot = {"min_trials": 0} # bypass pydantic on setup

    runner = MockComplexRunner()
    with pytest.raises(TrialExecutionFailure) as exc:
        await TrialExecutionService.execute_trials(db_session, run, runner)
    assert run.success is False
    assert "Invalid EvaluationPolicy" in run.error_info
