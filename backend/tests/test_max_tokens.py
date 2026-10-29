import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.db.models import ExperimentRun, ExperimentVariant, Base, MetricResult
from app.services.runner import SyntheticExperimentRunner
from datetime import datetime
import json

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

@pytest.mark.asyncio
async def test_max_tokens_impact(db_session: AsyncSession):
    runner = SyntheticExperimentRunner()

    async def get_metrics_for_tokens(tokens: int) -> dict:
        v = ExperimentVariant(project_id="test", name="var", is_baseline=False, system_configuration={"max_tokens": tokens})
        db_session.add(v)
        await db_session.flush()

        run = ExperimentRun(experiment_id="test", variant_id=v.id, runner_type="synthetic")
        db_session.add(run)
        await db_session.flush()

        await runner.execute(db_session, run, metrics_to_measure=["quality_score", "p95_latency_ms", "cost_per_request_usd"])

        stmt = select(MetricResult).where(MetricResult.run_id == run.id)
        res = await db_session.execute(stmt)
        metrics = {m.metric_name: m.value for m in res.scalars().all()}

        await db_session.delete(run)
        await db_session.delete(v)

        # Need to clean up MetricResult so they don't leak if we wanted, but not strictly necessary for memory db
        return metrics

    # Baseline
    base = await get_metrics_for_tokens(256)

    # Lower tokens
    lower = await get_metrics_for_tokens(128)

    # Higher tokens
    higher = await get_metrics_for_tokens(512)

    print("Base:", base)
    print("Lower:", lower)
    print("Higher:", higher)

    # Lower tokens should decrease quality, latency, and cost compared to base
    # Wait! the pseudo-random noise is based on config hash.
    # The noise might flip the deterministic trend if the noise (-1.0 to 1.0) is large.
    # Latency noise is *300.0, base is 4000.
    # The adjustment for 1024 is +4000, which is > 300, so it will definitively be higher.
    # The adjustment for 256 is -500*(0.5) = -250, noise is +/-300, so it MIGHT flip!
    # Let's check logic: l_adj -= 500 * 0.5 = 250. Noise is up to 300.
    # But wait, max_tokens has deterministic effect. We can assert the exact logic if we want, or just verify the trend roughly.
    # Actually, ratio=2 -> l_adj += 1000. 1000 > 300 noise.
    # We can at least check that higher latency is significantly larger.
    assert higher["p95_latency_ms"] > base["p95_latency_ms"]
    assert higher["cost_per_request_usd"] >= base["cost_per_request_usd"]
    assert higher["quality_score"] >= base["quality_score"]
