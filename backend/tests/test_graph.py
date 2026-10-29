import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Project, ResearchSession, Experiment, Decision
from app.services.strategy import ResearchStrategyService

from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from app.db.models import Base
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

client = TestClient(app)

@pytest.fixture
async def sample_project(db_session: AsyncSession):
    p = Project(name="Test Graph", objective="Test", constraints=[{"metric_name": "quality_score", "operator": ">=", "required_value": 90.0}])
    db_session.add(p)
    await db_session.commit()
    return p

@pytest.fixture
async def sample_session(db_session: AsyncSession, sample_project):
    rs = ResearchSession(project_id=sample_project.id)
    db_session.add(rs)
    await db_session.commit()
    return rs

@pytest.mark.asyncio
async def test_empty_graph(db_session: AsyncSession, sample_session, sample_project):
    from app.api.v1.research import get_research_graph
    data = await get_research_graph(sample_project.id, db_session)
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["type"] == "objective"
    assert len(data["edges"]) == 0

@pytest.mark.asyncio
async def test_graph_with_experiments(db_session: AsyncSession, sample_session, sample_project):
    from app.api.v1.research import get_research_graph
    # Add retained experiment
    exp1 = Experiment(project_id=sample_project.id, name="Exp 1", experiment_type="autonomous", candidate_description="desc 1", adopted=True, status="completed")
    db_session.add(exp1)
    await db_session.flush()
    d1 = Decision(experiment_id=exp1.id, result="RETAIN", rationale="Good")
    db_session.add(d1)

    # Add rejected experiment
    exp2 = Experiment(project_id=sample_project.id, name="Exp 2", experiment_type="autonomous", candidate_description="desc 2", adopted=False, status="completed")
    db_session.add(exp2)
    await db_session.flush()
    d2 = Decision(experiment_id=exp2.id, result="REJECT", rationale="Bad")
    db_session.add(d2)

    await db_session.commit()

    data = await get_research_graph(sample_project.id, db_session)
    assert len(data["nodes"]) == 3
    assert len(data["edges"]) == 2

    edges = data["edges"]
    assert edges[0]["source"] == "root"
    assert edges[0]["target"] == exp1.id
    assert edges[1]["source"] == exp1.id
    assert edges[1]["target"] == exp2.id

@pytest.mark.asyncio
async def test_strategy_engine(db_session: AsyncSession, sample_project):
    res = await ResearchStrategyService.determine_strategy(db_session, sample_project.id, [], [])
    assert "target_constraint" in res
    assert "unexplored_dimensions" in res
