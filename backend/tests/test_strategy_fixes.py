import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Project, Constraint, MetricResult, ExperimentVariant
from app.services.strategy import ResearchStrategyService
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from app.db.models import Base

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

@pytest.mark.asyncio
async def test_strategy_handles_missing_metrics(db_session: AsyncSession):
    # Setup constraints but NO metrics
    constraints = [
        Constraint(metric_name="latency", operator="<=", required_value=100.0),
        Constraint(metric_name="quality", operator=">=", required_value=90.0)
    ]

    # Missing metrics scenario
    res = await ResearchStrategyService.determine_strategy(db_session, "dummy_proj", constraints, [])

    assert res["target_constraint"] in ["latency", "quality"]
    assert res["gap"] in [100.0, 90.0]
    assert res["current_value"] == 0.0

@pytest.mark.asyncio
async def test_strategy_handles_partial_metrics(db_session: AsyncSession):
    constraints = [
        Constraint(metric_name="latency", operator="<=", required_value=100.0),
        Constraint(metric_name="quality", operator=">=", required_value=90.0)
    ]

    # Provide latency metric, but quality is missing
    # latency gap = 50 / 100 = 0.5
    # quality gap should be 1.0 (missing)
    metrics = [
        MetricResult(metric_name="latency", value=150.0, unit="ms", direction="down", sample_size=1, source="test", run_id="run1")
    ]

    res = await ResearchStrategyService.determine_strategy(db_session, "dummy_proj", constraints, metrics)

    # Quality should be selected because it's missing (gap 1.0 > 0.5)
    assert res["target_constraint"] == "quality"
    assert res["gap"] == 90.0
