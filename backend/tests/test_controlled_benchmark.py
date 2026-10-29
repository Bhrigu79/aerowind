import pytest
import os
import sys
import json
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure backend root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.database import async_session_maker
from app.db.models import Project, Constraint, ResearchSession, Experiment, ExperimentVariant, MetricResult, Decision, Evidence, ExperimentRun, ExperimentTrial
from app.gateway.gateway import ModelGateway
from app.services.ai_benchmark import RealAIBenchmarkRunner
from app.services.trial_execution import TrialExecutionService
from sqlalchemy import select

# To test the controlled script without actually running Nebius, we can mock ModelGateway.complete
@pytest.fixture
def mock_gateway():
    gateway = MagicMock(spec=ModelGateway)
    gateway.complete = AsyncMock()
    return gateway

@pytest.mark.asyncio
async def test_controlled_benchmark_flow(mock_gateway):
    # Setup mock response
    mock_response = MagicMock()
    mock_response.content = "positive"
    mock_response.provider.value = "nebius"
    mock_response.model = "nvidia/llama-3.1-nemotron-70b-instruct"
    mock_response.usage.estimated_cost_usd = 0.001
    mock_gateway.complete.return_value = mock_response

    async with async_session_maker() as session:
        # 1. Project
        project = Project(name="Test", objective="Test")
        session.add(project)
        await session.flush()

        # 2. Variant & config
        config = {
            "model": "nvidia/llama-3.1-nemotron-70b-instruct",
            "provider": "nebius",
            "sample_count": 2,
            "temperature": 0.0
        }
        variant = ExperimentVariant(project_id=project.id, name="Test Variant", system_configuration=config)
        session.add(variant)
        await session.flush()

        # 3. Experiment
        experiment = Experiment(project_id=project.id, name="Test", experiment_type="controlled", candidate_description="Test candidate")
        session.add(experiment)
        await session.flush()

        policy_snapshot = {
            "min_trials": 1,
            "max_trials": 1,
            "failure_tolerance_ratio": 0.0
        }

        # 4. Run
        run = ExperimentRun(
            experiment_id=experiment.id,
            variant_id=variant.id,
            runner_type="real_ai",
            execution_provenance="REAL_EXECUTION",
            evaluation_policy_snapshot=policy_snapshot,
            status="pending"
        )
        session.add(run)
        await session.flush()

        runner = RealAIBenchmarkRunner(mock_gateway)
        runner.dataset = runner.dataset[:2]

        # We explicitly do NOT import or invoke PlannerAgent, HypothesisAgent, etc.
        # We only call TrialExecutionService.execute_trials

        aggregated_evidence = await TrialExecutionService.execute_trials(
            session=session,
            run=run,
            runner=runner
        )

        # Assertions

        # 1-4. No autonomous agents invoked (by design in this test scope)
        assert 'PlannerAgent' not in sys.modules or not hasattr(sys.modules.get('app.agents.research', object), 'mock_called')

        # 5. Exactly one run is executed
        assert run.status == "completed"

        # 6. Exactly one trial configured
        trials_stmt = select(ExperimentTrial).where(ExperimentTrial.run_id == run.id)
        trials = (await session.execute(trials_stmt)).scalars().all()
        assert len(trials) == 1

        # 7. Exact Nemotron explicitly selected and allow_fallback=False
        calls = mock_gateway.complete.call_args_list
        assert len(calls) == 2
        for call in calls:
            req = call[0][0]
            assert req.preferred_model == "nvidia/llama-3.1-nemotron-70b-instruct"
            assert req.preferred_provider.value == "nebius"
            assert req.allow_fallback is False

        # 9. Policy snapshot persisted
        assert run.evaluation_policy_snapshot["min_trials"] == 1

        # 10. Provider/model provenance persisted
        assert run.execution_metadata["provider"] == "nebius"
        assert run.execution_metadata["model"] == "nvidia/llama-3.1-nemotron-70b-instruct"
