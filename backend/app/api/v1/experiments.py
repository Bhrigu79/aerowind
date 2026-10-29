"""
AEROWIND API v1 — Experiments Router
======================================
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.database import get_db_session
from app.db.models import Experiment as ExperimentModel, ExperimentEvent as ExperimentEventModel
from app.schemas.experiment import (
    ExperimentCreate,
    ExperimentDetail,
    ExperimentResponse,
    ExperimentStatus,
    MetricSnapshot,
)

router = APIRouter(prefix="/experiments", tags=["Experiments"])
logger = get_logger(__name__)


def _serialize_experiment(e: ExperimentModel) -> ExperimentResponse:
    return ExperimentResponse(
        id=e.id,
        project_id=e.project_id,
        hypothesis_id=e.hypothesis_id,
        name=e.name,
        description=e.description,
        experiment_type=e.experiment_type,
        status=ExperimentStatus(e.status),
        candidate_description=e.candidate_description,
        sequence_number=e.sequence_number,
        created_at=e.created_at,
        started_at=e.started_at,
        completed_at=e.completed_at,
        duration_seconds=e.duration_seconds,
        baseline_metrics=e.baseline_metrics,
        candidate_metrics=e.candidate_metrics,
        conclusion=e.conclusion,
        hypothesis_confirmed=e.hypothesis_confirmed,
        adopted=e.adopted,
        regression_detected=e.regression_detected,
        error_message=e.error_message,
    )


def _serialize_experiment_detail(e: ExperimentModel, events: list[ExperimentEventModel]) -> ExperimentDetail:
    resp = _serialize_experiment(e)
    # Convert base response to detail
    detail_data = resp.model_dump()
    detail_data["candidate_changes"] = e.candidate_changes or {}
    detail_data["log_entries"] = [
        {
            "id": ev.id,
            "timestamp": ev.timestamp,
            "stage": ev.stage,
            "event_type": ev.event_type,
            "message": ev.message,
            "metadata": ev.metadata_data,
        }
        for ev in events
    ]
    detail_data["evidence_artifacts"] = []
    detail_data["agent_reasoning"] = None
    return ExperimentDetail(**detail_data)


@router.post("/", response_model=ExperimentResponse, status_code=201)
async def create_experiment(
    body: ExperimentCreate,
    session: AsyncSession = Depends(get_db_session),
) -> ExperimentResponse:
    """Create a new experiment within a project."""

    # Get sequence number
    stmt = select(ExperimentModel).where(ExperimentModel.project_id == body.project_id).order_by(ExperimentModel.sequence_number.desc()).limit(1)
    result = await session.execute(stmt)
    last_exp = result.scalars().first()
    seq = (last_exp.sequence_number + 1) if last_exp else 1

    experiment = ExperimentModel(
        project_id=body.project_id,
        hypothesis_id=body.hypothesis_id,
        name=body.name,
        description=body.description,
        experiment_type=body.experiment_type.value,
        status=ExperimentStatus.PENDING.value,
        candidate_description=body.candidate_description,
        candidate_changes=body.candidate_changes,
        sequence_number=seq,
    )

    session.add(experiment)
    await session.commit()
    await session.refresh(experiment)
    logger.info(
        "experiment.created",
        experiment_id=experiment.id,
        project_id=body.project_id,
        type=body.experiment_type,
    )
    return _serialize_experiment(experiment)


@router.get("/", response_model=list[ExperimentResponse])
async def list_experiments(
    project_id: Annotated[str | None, Query()] = None,
    status: Annotated[ExperimentStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_db_session),
) -> list[ExperimentResponse]:
    """List experiments with optional filtering."""
    stmt = select(ExperimentModel).order_by(ExperimentModel.created_at.desc()).offset(offset).limit(limit)
    if project_id:
        stmt = stmt.where(ExperimentModel.project_id == project_id)
    if status:
        stmt = stmt.where(ExperimentModel.status == status.value)

    result = await session.execute(stmt)
    experiments = result.scalars().all()
    return [_serialize_experiment(e) for e in experiments]


@router.get("/{experiment_id}", response_model=ExperimentDetail)
async def get_experiment(
    experiment_id: Annotated[str, Path()],
    session: AsyncSession = Depends(get_db_session),
) -> ExperimentDetail:
    """Get full experiment detail including logs and evidence."""
    experiment = await session.get(ExperimentModel, experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")

    stmt = select(ExperimentEventModel).where(ExperimentEventModel.experiment_id == experiment_id).order_by(ExperimentEventModel.timestamp.asc())
    result = await session.execute(stmt)
    events = list(result.scalars().all())

    return _serialize_experiment_detail(experiment, events)


@router.get("/{experiment_id}/events")
async def get_experiment_events(
    experiment_id: Annotated[str, Path()],
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """Get events/logs for a specific experiment."""
    stmt = select(ExperimentEventModel).where(ExperimentEventModel.experiment_id == experiment_id).order_by(ExperimentEventModel.timestamp.asc())
    result = await session.execute(stmt)
    events = result.scalars().all()
    return [
        {
            "id": ev.id,
            "experiment_id": ev.experiment_id,
            "timestamp": ev.timestamp,
            "stage": ev.stage,
            "event_type": ev.event_type,
            "message": ev.message,
            "metadata": ev.metadata_data,
        }
        for ev in events
    ]


@router.post("/{experiment_id}/start", response_model=ExperimentResponse)
async def start_experiment(
    experiment_id: Annotated[str, Path()],
    session: AsyncSession = Depends(get_db_session),
) -> ExperimentResponse:
    """Transition experiment to RUNNING state."""
    experiment = await session.get(ExperimentModel, experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")

    if experiment.status != ExperimentStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail=f"Experiment is '{experiment.status}', not PENDING",
        )

    experiment.status = ExperimentStatus.RUNNING.value
    experiment.started_at = datetime.utcnow()

    # Create start event
    event = ExperimentEventModel(
        experiment_id=experiment_id,
        stage=ExperimentStatus.RUNNING.value,
        event_type="EXPERIMENT_STARTED",
        message="Experiment started.",
        metadata_data={},
    )
    session.add(event)

    await session.commit()
    await session.refresh(experiment)
    logger.info("experiment.started", experiment_id=experiment_id)
    return _serialize_experiment(experiment)


@router.post("/{experiment_id}/cancel", response_model=ExperimentResponse)
async def cancel_experiment(
    experiment_id: Annotated[str, Path()],
    session: AsyncSession = Depends(get_db_session),
) -> ExperimentResponse:
    """Cancel a running experiment."""
    experiment = await session.get(ExperimentModel, experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")

    if experiment.status not in (ExperimentStatus.PENDING.value, ExperimentStatus.RUNNING.value):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel experiment in '{experiment.status}' state",
        )

    experiment.status = ExperimentStatus.CANCELLED.value
    experiment.completed_at = datetime.utcnow()

    # Create cancel event
    event = ExperimentEventModel(
        experiment_id=experiment_id,
        stage=ExperimentStatus.CANCELLED.value,
        event_type="EXPERIMENT_CANCELLED",
        message="Experiment cancelled by user.",
        metadata_data={},
    )
    session.add(event)

    await session.commit()
    await session.refresh(experiment)
    logger.info("experiment.cancelled", experiment_id=experiment_id)
    return _serialize_experiment(experiment)


@router.patch("/{experiment_id}/metrics", response_model=ExperimentResponse)
async def update_experiment_metrics(
    experiment_id: Annotated[str, Path()],
    baseline: MetricSnapshot | None = None,
    candidate: MetricSnapshot | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> ExperimentResponse:
    """Update baseline or candidate metrics for an experiment."""
    experiment = await session.get(ExperimentModel, experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")

    if baseline:
        experiment.baseline_metrics = baseline.model_dump()
    if candidate:
        experiment.candidate_metrics = candidate.model_dump()

    await session.commit()
    await session.refresh(experiment)
    return _serialize_experiment(experiment)
