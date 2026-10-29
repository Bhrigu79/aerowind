"""
AEROWIND Pydantic Schemas — Projects
======================================
A Project is the top-level unit: a user's optimization objective.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class TargetConstraint(BaseModel):
    """A single measurable constraint on the system being optimized."""

    metric: str  # e.g. "quality_score", "p95_latency_ms", "cost_per_request_usd"
    operator: str  # ">=", "<=", ">", "<", "=="
    value: float
    unit: str | None = None  # e.g. "ms", "USD", "percent"
    description: str | None = None


class ProjectCreate(BaseModel):
    """Request body for creating a new project."""

    name: str = Field(..., min_length=3, max_length=200)
    description: str | None = None
    # The user's natural language objective
    objective: str = Field(..., min_length=10)
    # Measurable constraints that AEROWIND must satisfy
    constraints: list[TargetConstraint] = Field(default_factory=list)
    # Optional: pointer to the system being optimized
    target_system_description: str | None = None
    target_system_code: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    objective: str | None = None
    constraints: list[TargetConstraint] | None = None
    status: ProjectStatus | None = None


class ProjectResponse(BaseModel):
    """Full project representation returned to the frontend."""

    id: str
    name: str
    description: str | None
    objective: str
    constraints: list[TargetConstraint]
    target_system_description: str | None
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime

    # Summary stats (computed)
    experiment_count: int = 0
    hypothesis_count: int = 0
    best_quality_score: float | None = None
    best_latency_ms: float | None = None
    estimated_total_cost_usd: float = 0.0

    model_config = {"from_attributes": True}
