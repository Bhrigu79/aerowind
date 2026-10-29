import pytest
from app.db.models import Project, Constraint, MetricResult, Experiment, ExperimentRun, ExperimentVariant
from app.services.progress import ObjectiveProgressService
from app.services.memory import ResearchMemoryService
from app.domain.types import ConstraintOperator
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_objective_progress():
    constraints = [
        Constraint(metric_name="quality_score", operator=ConstraintOperator.GTE.value, required_value=0.92),
        Constraint(metric_name="p95_latency_ms", operator=ConstraintOperator.LTE.value, required_value=2000.0)
    ]

    baseline_metrics = [
        MetricResult(metric_name="quality_score", value=0.88),
        MetricResult(metric_name="p95_latency_ms", value=2400.0)
    ]

    current_metrics = [
        MetricResult(metric_name="quality_score", value=0.91),
        MetricResult(metric_name="p95_latency_ms", value=1800.0)
    ]

    progress = ObjectiveProgressService.calculate_progress(constraints, baseline_metrics, current_metrics)

    assert progress["all_passed"] is False

    q_prog = progress["metrics_progress"]["quality_score"]
    assert q_prog["status"] == "failing"
    assert q_prog["gap"] == pytest.approx(0.01)
    assert q_prog["improvement_from_baseline"] == pytest.approx(0.03)

    l_prog = progress["metrics_progress"]["p95_latency_ms"]
    assert l_prog["status"] == "passing"
    assert l_prog["gap"] == 0
    assert l_prog["improvement_from_baseline"] == pytest.approx(-600.0)
