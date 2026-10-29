"""
AEROWIND API v1 — Projects Router
===================================
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.database import get_db_session
from app.db.models import Project as ProjectModel
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectStatus, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["Projects"])
logger = get_logger(__name__)


def _serialize_project(p: ProjectModel) -> ProjectResponse:
    return ProjectResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        objective=p.objective,
        target_system_description=p.target_system_description,
        constraints=p.constraints,
        status=ProjectStatus(p.status),
        created_at=p.created_at,
        updated_at=p.updated_at,
        experiment_count=p.experiment_count,
        hypothesis_count=p.hypothesis_count,
        best_quality_score=p.best_quality_score,
        best_latency_ms=p.best_latency_ms,
        estimated_total_cost_usd=p.estimated_total_cost_usd,
    )


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Create a new AEROWIND optimization project."""
    project = ProjectModel(
        name=body.name,
        description=body.description,
        objective=body.objective,
        constraints=[c.model_dump() for c in body.constraints],
        target_system_description=body.target_system_description,
        status=ProjectStatus.DRAFT.value,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    logger.info("project.created", project_id=project.id, name=project.name)
    return _serialize_project(project)


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(
    status: Annotated[ProjectStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_db_session),
) -> list[ProjectResponse]:
    """List all projects, optionally filtered by status."""
    stmt = select(ProjectModel).order_by(ProjectModel.created_at.desc()).offset(offset).limit(limit)
    if status:
        stmt = stmt.where(ProjectModel.status == status.value)

    result = await session.execute(stmt)
    projects = result.scalars().all()
    return [_serialize_project(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: Annotated[str, Path()],
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Get a project by ID."""
    project = await session.get(ProjectModel, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return _serialize_project(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: Annotated[str, Path()],
    body: ProjectUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Update a project."""
    project = await session.get(ProjectModel, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    updates = body.model_dump(exclude_none=True)
    if "constraints" in updates:
        updates["constraints"] = [c for c in updates["constraints"]]

    for key, value in updates.items():
        setattr(project, key, value)

    await session.commit()
    await session.refresh(project)
    logger.info("project.updated", project_id=project_id, updates=list(updates.keys()))
    return _serialize_project(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: Annotated[str, Path()],
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a project and all associated data."""
    project = await session.get(ProjectModel, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    await session.delete(project)
    await session.commit()
    logger.info("project.deleted", project_id=project_id)
