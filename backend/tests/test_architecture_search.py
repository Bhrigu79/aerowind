import pytest
from app.services.runner import SyntheticExperimentRunner
from app.db.models import ExperimentRun, ExperimentVariant
from app.domain.types import MetricDirection
from app.services.strategy import ResearchStrategyService
from app.services.memory import ResearchMemoryService

@pytest.mark.asyncio
async def test_synthetic_runner_dimensions():
    runner = SyntheticExperimentRunner()

    class MockVariant:
        def __init__(self, config):
            self.system_configuration = config

    class MockRun:
        def __init__(self, variant):
            self.id = "run-123"
            self.variant = variant
            self.started_at = None
            self.completed_at = None
            self.success = False
            self.status = "pending"

    class MockSession:
        def __init__(self):
            self.added = []
        def add(self, obj):
            self.added.append(obj)

    # Baseline
    run_base = MockRun(MockVariant({"model": "small", "retrieval_enabled": False, "temperature": 0.7}))
    session_base = MockSession()
    await runner.execute(session_base, run_base)

    base_q = next((m.value for m in session_base.added if m.metric_name == "quality_score"), 0)
    base_l = next((m.value for m in session_base.added if m.metric_name == "p95_latency_ms"), 0)
    base_c = next((m.value for m in session_base.added if m.metric_name == "cost_per_request_usd"), 0)

    # Candidate with retrieval
    run_cand = MockRun(MockVariant({"model": "small", "retrieval_enabled": True, "temperature": 0.7}))
    session_cand = MockSession()
    await runner.execute(session_cand, run_cand)

    cand_q = next((m.value for m in session_cand.added if m.metric_name == "quality_score"), 0)
    cand_l = next((m.value for m in session_cand.added if m.metric_name == "p95_latency_ms"), 0)
    cand_c = next((m.value for m in session_cand.added if m.metric_name == "cost_per_request_usd"), 0)

    # Assert retrieval increases quality but also increases latency and cost
    assert cand_q > base_q
    assert cand_l > base_l
    assert cand_c > base_c

    # Candidate with draft_critique pipeline
    run_dc = MockRun(MockVariant({"model": "small", "pipeline_mode": "draft_critique", "temperature": 0.7}))
    session_dc = MockSession()
    await runner.execute(session_dc, run_dc)

    dc_q = next((m.value for m in session_dc.added if m.metric_name == "quality_score"), 0)
    dc_l = next((m.value for m in session_dc.added if m.metric_name == "p95_latency_ms"), 0)

    assert dc_q > base_q
    assert dc_l > base_l
@pytest.mark.asyncio
async def test_strategy_engine_objective_aware():
    class MockConstraint:
        def __init__(self, name, req, op):
            self.metric_name = name
            self.required_value = req
            self.operator = op

    constraints = [
        MockConstraint("quality", 95.0, ">="),
        MockConstraint("p95_latency_ms", 2000.0, "<=")
    ]

    class MockMetric:
        def __init__(self, name, val):
            self.metric_name = name
            self.value = val

    # Case 1: Quality is very bad, Latency is okay
    metrics = [
        MockMetric("quality", 80.0),
        MockMetric("p95_latency_ms", 1900.0)
    ]

    class MockSession:
        def __init__(self):
            self.variants = []
        async def execute(self, stmt):
            class MockResult:
                def scalars(self):
                    class MockScalars:
                        def all(self):
                            return []
                    return MockScalars()
            return MockResult()

    strategy = await ResearchStrategyService.determine_strategy(MockSession(), "proj1", constraints, metrics)
    assert strategy["target_constraint"] == "quality"
    assert strategy["selected_dimension"] in ["prompt_strategy", "few_shot_count", "retrieval_enabled", "pipeline_mode", "model", "temperature"]

    # Case 2: Quality is good, Latency is very bad
    metrics = [
        MockMetric("quality", 96.0),
        MockMetric("p95_latency_ms", 5000.0)
    ]
    strategy = await ResearchStrategyService.determine_strategy(MockSession(), "proj1", constraints, metrics)
    assert strategy["target_constraint"] == "p95_latency_ms"
    assert strategy["selected_dimension"] in ["retrieval_enabled", "pipeline_mode", "model", "max_tokens"]
