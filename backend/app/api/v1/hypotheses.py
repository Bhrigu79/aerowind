"""
AEROWIND API v1 — Hypotheses Router
======================================
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.database import get_db_session
from app.db.models import Hypothesis as HypothesisModel
from app.schemas.experiment import (
    HypothesisCreate,
    HypothesisResponse,
    HypothesisStatus,
)

router = APIRouter(prefix="/hypotheses", tags=["Hypotheses"])
logger = get_logger(__name__)


def _serialize_hypothesis(h: HypothesisModel) -> HypothesisResponse:
    return HypothesisResponse(
        id=h.id,
        project_id=h.project_id,
        statement=h.statement,
        rationale=h.rationale,
        expected_improvement=h.expected_improvement,
        status=HypothesisStatus(h.status),
        priority=h.priority,
        created_at=h.created_at,
        updated_at=h.updated_at,
        conclusion=h.conclusion,
        evidence_summary=h.evidence_summary,
    )


@router.post("/", response_model=HypothesisResponse, status_code=201)
async def create_hypothesis(
    body: HypothesisCreate,
    session: AsyncSession = Depends(get_db_session),
) -> HypothesisResponse:
    """Create a new hypothesis for a project."""
    hypothesis = HypothesisModel(
        project_id=body.project_id,
        statement=body.statement,
        rationale=body.rationale,
        expected_improvement=body.expected_improvement,
        status=HypothesisStatus.PENDING.value,
        priority=body.priority,
    )
    session.add(hypothesis)
    await session.commit()
    await session.refresh(hypothesis)
    logger.info("hypothesis.created", hypothesis_id=hypothesis.id, project_id=body.project_id)
    return _serialize_hypothesis(hypothesis)


@router.get("/", response_model=list[HypothesisResponse])
async def list_hypotheses(
    project_id: Annotated[str | None, Query()] = None,
    status: Annotated[HypothesisStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    session: AsyncSession = Depends(get_db_session),
) -> list[HypothesisResponse]:
    """List hypotheses with optional filtering."""
    stmt = select(HypothesisModel).order_by(HypothesisModel.priority.desc(), HypothesisModel.created_at.desc()).limit(limit)
    if project_id:
        stmt = stmt.where(HypothesisModel.project_id == project_id)
    if status:
        stmt = stmt.where(HypothesisModel.status == status.value)

    result = await session.execute(stmt)
    hypotheses = result.scalars().all()
    return [_serialize_hypothesis(h) for h in hypotheses]


@router.get("/{hypothesis_id}", response_model=HypothesisResponse)
async def get_hypothesis(
    hypothesis_id: Annotated[str, Path()],
    session: AsyncSession = Depends(get_db_session),
) -> HypothesisResponse:
    """Get a hypothesis by ID."""
    hypothesis = await session.get(HypothesisModel, hypothesis_id)
    if not hypothesis:
        raise HTTPException(status_code=404, detail=f"Hypothesis '{hypothesis_id}' not found")
    return _serialize_hypothesis(hypothesis)
