"""
AEROWIND Pydantic Schemas — Experiments & Hypotheses
======================================================
Experiments are the core unit of AEROWIND's scientific process.

lifecycle:
  PENDING → RUNNING → MEASURING → ANALYZING → COMPLETED | FAILED | REJECTED
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Hypothesis ────────────────────────────────────────────────────────────────

class HypothesisStatus(str, Enum):
    PENDING = "pending"       # Waiting to be tested
    TESTING = "testing"       # Experiment is running
    CONFIRMED = "confirmed"   # Evidence supports the hypothesis
    REJECTED = "rejected"     # Evidence does not support the hypothesis
    INCONCLUSIVE = "inconclusive"  # Insufficient or mixed evidence


class HypothesisCreate(BaseModel):
    project_id: str
    # Human-readable statement of the hypothesis
    statement: str = Field(..., min_length=10)
    # Rationale / evidence that motivated this hypothesis
    rationale: str | None = None
    # Expected impact (what the agent predicts will improve)
    expected_improvement: dict[str, Any] = Field(default_factory=dict)
    # Priority for scheduling (higher = sooner)
    priority: int = Field(default=0, ge=0, le=100)


class HypothesisResponse(BaseModel):
    id: str
    project_id: str
    statement: str
    rationale: str | None
    expected_improvement: dict[str, Any]
    status: HypothesisStatus
    priority: int
    created_at: datetime
    updated_at: datetime
    # Filled after testing
    conclusion: str | None = None
    evidence_summary: str | None = None

    model_config = {"from_attributes": True}


# ── Experiment ────────────────────────────────────────────────────────────────

class ExperimentStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    HYPOTHESIS = "hypothesis"
    DESIGNING = "designing"
    PENDING = "pending"
    BUILDING = "building"
    RUNNING = "running"
    MEASURING = "measuring"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExperimentType(str, Enum):
    # Prompt engineering
    PROMPT_OPTIMIZATION = "prompt_optimization"
    # Model swap
    MODEL_SWAP = "model_swap"
    # Architecture change (sequential → parallel, etc.)
    ARCHITECTURE_CHANGE = "architecture_change"
    # Configuration tuning
    CONFIG_TUNING = "config_tuning"
    # Caching strategy
    CACHING = "caching"
    # Retrieval strategy
    RETRIEVAL = "retrieval"
    # Code optimization
    CODE_OPTIMIZATION = "code_optimization"
    # Full system redesign
    SYSTEM_REDESIGN = "system_redesign"
    # Baseline measurement only
    BASELINE = "baseline"


class MetricSnapshot(BaseModel):
    """A snapshot of measured metrics at a point in time."""

    quality_score: float | None = None      # 0.0–1.0 or 0–100
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    avg_latency_ms: float | None = None
    throughput_rps: float | None = None     # requests per second
    cost_per_request_usd: float | None = None
    total_cost_usd: float | None = None
    error_rate: float | None = None         # 0.0–1.0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    # Provider-level detail
    token_usage: dict[str, int] = Field(default_factory=dict)
    provider_breakdown: dict[str, Any] = Field(default_factory=dict)
    custom: dict[str, Any] = Field(default_factory=dict)

    source: str | None = None  # e.g., "synthetic", "real_ai_benchmark_v1", "nebius"


class ExperimentCreate(BaseModel):
    project_id: str
    hypothesis_id: str | None = None
    name: str = Field(..., min_length=3, max_length=200)
    description: str | None = None
    experiment_type: ExperimentType
    # The change being tested (human-readable)
    candidate_description: str
    # Actual changes: code diffs, config changes, prompt changes
    candidate_changes: dict[str, Any] = Field(default_factory=dict)


class ExperimentResponse(BaseModel):
    id: str
    project_id: str
    hypothesis_id: str | None
    name: str
    description: str | None
    experiment_type: ExperimentType
    status: ExperimentStatus
    candidate_description: str

    # Sequence number within the project
    sequence_number: int = 0

    # Timing
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None

    # Results
    baseline_metrics: MetricSnapshot | None = None
    candidate_metrics: MetricSnapshot | None = None

    # Analysis
    conclusion: str | None = None
    hypothesis_confirmed: bool | None = None
    adopted: bool = False
    regression_detected: bool = False

    # Error details
    error_message: str | None = None

    model_config = {"from_attributes": True}


class ExperimentDetail(ExperimentResponse):
    """Full experiment detail including logs and evidence."""

    candidate_changes: dict[str, Any] = Field(default_factory=dict)
    log_entries: list[dict[str, Any]] = Field(default_factory=list)
    evidence_artifacts: list[str] = Field(default_factory=list)
    agent_reasoning: str | None = None
