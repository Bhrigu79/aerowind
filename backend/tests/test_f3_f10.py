import pytest
import json
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base, Project, Constraint, ExperimentRun, MetricResult
from app.domain.types import ConstraintOperator
from app.services.progress import ObjectiveProgressService
from app.services.strategy import ResearchStrategyService
from app.services.nebius_runner import NebiusExperimentRunner
from app.services.runner import ExecutionFailure
from app.core.config_validator import ConfigurationValidator
from app.services.orchestrator import _configs_are_equal
import os

@pytest.fixture
async def real_db_session():
    # Use an actual file-based SQLite database to catch type errors
    # Memory DBs sometimes behave differently, but a file DB is best.
    db_path = "test_f10.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except PermissionError:
            pass

class TestF3ObjectiveProgress:
    @pytest.mark.asyncio
    async def test_progress_f3(self):
        c1 = Constraint(metric_name="quality", operator=ConstraintOperator.GTE.value, required_value=90.0)
        c2 = Constraint(metric_name="latency", operator=ConstraintOperator.LTE.value, required_value=2000.0)

        # 1. quality >= 90, actual 95 -> passing
        m1 = MetricResult(metric_name="quality", value=95.0)
        prog1 = ObjectiveProgressService.calculate_progress([c1], [], [m1])
        assert prog1["metrics_progress"]["quality"]["passed"] is True
        assert prog1["metrics_progress"]["quality"]["status"] == "passing"
        assert prog1["metrics_progress"]["quality"]["gap"] == 0

        # 2. quality >= 90, actual 85 -> failing
        m2 = MetricResult(metric_name="quality", value=85.0)
        prog2 = ObjectiveProgressService.calculate_progress([c1], [], [m2])
        assert prog2["metrics_progress"]["quality"]["passed"] is False
        assert prog2["metrics_progress"]["quality"]["status"] == "failing"
        assert prog2["metrics_progress"]["quality"]["gap"] == 5.0

        # 3. latency <= 2000, actual 1500 -> passing
        m3 = MetricResult(metric_name="latency", value=1500.0)
        prog3 = ObjectiveProgressService.calculate_progress([c2], [], [m3])
        assert prog3["metrics_progress"]["latency"]["passed"] is True

        # 4. latency <= 2000, actual 2500 -> failing
        m4 = MetricResult(metric_name="latency", value=2500.0)
        prog4 = ObjectiveProgressService.calculate_progress([c2], [], [m4])
        assert prog4["metrics_progress"]["latency"]["passed"] is False

        # 5. mixed objective
        prog5 = ObjectiveProgressService.calculate_progress([c1, c2], [], [m1, m4])
        assert prog5["metrics_progress"]["quality"]["passed"] is True
        assert prog5["metrics_progress"]["latency"]["passed"] is False

    @pytest.mark.asyncio
    async def test_strategy_f3(self, real_db_session: AsyncSession):
        proj = Project(name="Test Strategy F3", objective="test")
        real_db_session.add(proj)
        await real_db_session.flush()

        c1 = Constraint(project_id=proj.id, metric_name="quality", operator=ConstraintOperator.GTE.value, required_value=90.0)
        c2 = Constraint(project_id=proj.id, metric_name="latency", operator=ConstraintOperator.LTE.value, required_value=2000.0)
        real_db_session.add(c1)
        real_db_session.add(c2)
        await real_db_session.commit()

        m1 = MetricResult(metric_name="quality", value=95.0)
        m4 = MetricResult(metric_name="latency", value=2500.0)

        strategy = await ResearchStrategyService.determine_strategy(real_db_session, proj.id, [c1, c2], [m1, m4])

        # Strategy should prioritize latency, not quality
        assert "latency" in strategy["target_constraint"]
        assert strategy["gap"] == 500.0

        # 6. all constraints pass
        m3 = MetricResult(metric_name="latency", value=1500.0)
        strategy2 = await ResearchStrategyService.determine_strategy(real_db_session, proj.id, [c1, c2], [m1, m3])
        assert strategy2["gap"] == 0.0

class TestF10NebiusErrorPath:
    @pytest.mark.asyncio
    async def test_nebius_error_db_type(self, real_db_session: AsyncSession):
        from unittest.mock import patch

        run = ExperimentRun(experiment_id="test-123", variant_id="var-123", runner_type="nebius")
        real_db_session.add(run)
        await real_db_session.commit()

        from app.core.config import settings
        import sys
        from unittest.mock import patch, MagicMock

        # Mock SDK
        mock_sdk_class = MagicMock()

        with patch.object(settings, 'NEBIUS_EXEC_ENABLED', True), \
             patch.object(settings, 'NEBIUS_EXEC_SERVICE_ACCOUNT_ID', "mock"), \
             patch('app.services.nebius_runner.SDK', mock_sdk_class):
            runner = NebiusExperimentRunner()

        # Mocking the client create method to raise Exception
        with patch.object(runner, 'client') as mock_client:
            mock_client.create.side_effect = Exception("Simulated Nebius Crash")

            from app.schemas.execution import ExperimentExecutionSpec
            spec = ExperimentExecutionSpec(
                experiment_id="test-123",
                variant_id="var-123",
                runner_type="nebius",
                workload="test",
                entrypoint=["echo"],
                environment={}
            )

            with pytest.raises(ExecutionFailure) as exc:
                await runner.execute(real_db_session, run, spec)

            assert exc.value.failure_type == "INFRASTRUCTURE_ERROR"

        # Refetch the run
        await real_db_session.refresh(run)
        assert run.status == "failed"

        # Verify error_info is valid JSON string
        assert isinstance(run.error_info, str)
        error_dict = json.loads(run.error_info)
        assert error_dict["type"] == "INFRASTRUCTURE_ERROR"
        assert "Simulated Nebius Crash" in error_dict["message"]

class TestF2ConfigurationNormalization:
    def test_normalization_f2(self):
        # Baseline with omitted default
        baseline = {"temperature": 0.7} # max_tokens missing, default is 1024

        # Candidate with explicit same default
        candidate = {"temperature": 0.7, "max_tokens": 1024}

        assert _configs_are_equal(baseline, candidate)

        # Genuinely different default
        candidate2 = {"temperature": 0.7, "max_tokens": 512}
        assert not _configs_are_equal(baseline, candidate2)

        # Reordered keys
        candidate3 = {"max_tokens": 1024, "temperature": 0.7}
        assert _configs_are_equal(baseline, candidate3)
