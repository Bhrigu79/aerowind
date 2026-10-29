import pytest
from app.db.models import Project, Constraint, MetricResult, Experiment, ExperimentRun
from app.services.constraints import ConstraintEngine
from app.services.decision import DecisionEngine
from app.domain.types import DecisionResult, ConstraintOperator, ExperimentState
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_constraint_engine():
    # Setup constraints
    constraints = [
        Constraint(metric_name="quality_score", operator=ConstraintOperator.GTE.value, required_value=0.92),
        Constraint(metric_name="p95_latency_ms", operator=ConstraintOperator.LTE.value, required_value=2000.0)
    ]

    # Test pass
    metrics_pass = [
        MetricResult(metric_name="quality_score", value=0.95),
        MetricResult(metric_name="p95_latency_ms", value=1800.0)
    ]

    evals = ConstraintEngine.evaluate(constraints, metrics_pass)
    assert len(evals) == 2
    assert all(e.passed for e in evals)

    # Test fail
    metrics_fail = [
        MetricResult(metric_name="quality_score", value=0.90), # fail
        MetricResult(metric_name="p95_latency_ms", value=2100.0) # fail
    ]
    evals_fail = ConstraintEngine.evaluate(constraints, metrics_fail)
    assert not evals_fail[0].passed
    assert not evals_fail[1].passed

    # Test missing metric
    metrics_missing = [
        MetricResult(metric_name="quality_score", value=0.95)
    ]
    evals_missing = ConstraintEngine.evaluate(constraints, metrics_missing)
    assert any(e.missing_metric for e in evals_missing)


@pytest.mark.asyncio
async def test_decision_engine():
    experiment = Experiment()
    run_success = ExperimentRun(success=True)
    run_fail = ExperimentRun(success=False, error_info="Timeout")

    constraints = [
        Constraint(metric_name="quality_score", operator=ConstraintOperator.GTE.value, required_value=0.92)
    ]
    metrics = [MetricResult(metric_name="quality_score", value=0.95)]

    evals_pass = ConstraintEngine.evaluate(constraints, metrics)

    # Decision: Retain
    dec, msg = DecisionEngine.decide(experiment, run_success, evals_pass)
    assert dec == DecisionResult.RETAIN

    # Decision: Inconclusive (Run failed)
    dec, msg = DecisionEngine.decide(experiment, run_fail, evals_pass)
    assert dec == DecisionResult.INCONCLUSIVE

    # Decision: Reject (Failed constraint)
    metrics_fail = [MetricResult(metric_name="quality_score", value=0.85)]
    evals_fail = ConstraintEngine.evaluate(constraints, metrics_fail)
    dec, msg = DecisionEngine.decide(experiment, run_success, evals_fail)
    assert dec == DecisionResult.REJECT

@pytest.mark.asyncio
async def test_state_transitions():
    from app.services.state import ExperimentStateMachine, InvalidStateTransitionError
    from sqlalchemy.ext.asyncio import AsyncSession
    from unittest.mock import AsyncMock

    experiment = Experiment(status="draft")
    session = AsyncMock(spec=AsyncSession)

    # Valid
    await ExperimentStateMachine.transition(session, experiment, ExperimentState.PLANNED)
    assert experiment.status == "planned"

    # Invalid
    with pytest.raises(InvalidStateTransitionError):
        await ExperimentStateMachine.transition(session, experiment, ExperimentState.MEASURING)

@pytest.mark.asyncio
async def test_synthetic_runner():
    from app.services.runner import SyntheticExperimentRunner
    from unittest.mock import AsyncMock

    session = AsyncMock(spec=AsyncSession)
    run = ExperimentRun(id="run123")
    runner = SyntheticExperimentRunner()

    await runner.execute(session, run, is_candidate=True)

    assert run.status == "completed"
    assert run.success is True
    assert run.started_at is not None
    assert run.completed_at is not None
    assert session.add.called
