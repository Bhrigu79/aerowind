from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    objective: Mapped[str] = mapped_column(String, nullable=False)
    target_system_description: Mapped[str | None] = mapped_column(String, nullable=True)
    constraints: Mapped[list[dict]] = mapped_column(JSON, default=list) # Legacy JSON
    status: Mapped[str] = mapped_column(String, default="draft")

    experiment_count: Mapped[int] = mapped_column(Integer, default=0)
    hypothesis_count: Mapped[int] = mapped_column(Integer, default=0)
    best_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    experiments: Mapped[list["Experiment"]] = relationship("Experiment", back_populates="project", cascade="all, delete-orphan")
    hypotheses: Mapped[list["Hypothesis"]] = relationship("Hypothesis", back_populates="project", cascade="all, delete-orphan")
    db_constraints: Mapped[list["Constraint"]] = relationship("Constraint", back_populates="project", cascade="all, delete-orphan")


class Constraint(Base):
    __tablename__ = "constraints"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    metric_name: Mapped[str] = mapped_column(String, nullable=False)
    operator: Mapped[str] = mapped_column(String, nullable=False)
    required_value: Mapped[float] = mapped_column(Float, nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="db_constraints")


class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id", ondelete="CASCADE"))

    # Legacy fields
    statement: Mapped[str] = mapped_column(String, nullable=False)
    rationale: Mapped[str | None] = mapped_column(String, nullable=True)
    expected_improvement: Mapped[dict] = mapped_column(JSON, default=dict)

    # New structured fields
    claim: Mapped[str | None] = mapped_column(String, nullable=True)
    expected_effect: Mapped[str | None] = mapped_column(String, nullable=True)
    target_metric: Mapped[str | None] = mapped_column(String, nullable=True)
    expected_direction: Mapped[str | None] = mapped_column(String, nullable=True)
    expected_magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    independent_variable: Mapped[str | None] = mapped_column(String, nullable=True)
    control_description: Mapped[str | None] = mapped_column(String, nullable=True)
    candidate_description: Mapped[str | None] = mapped_column(String, nullable=True)
    risks: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, default="pending")
    priority: Mapped[int] = mapped_column(Integer, default=50)
    conclusion: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence_summary: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="hypotheses")
    experiments: Mapped[list["Experiment"]] = relationship("Experiment", back_populates="hypothesis")


class ExperimentPlan(Base):
    __tablename__ = "experiment_plans"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = mapped_column(String, ForeignKey("experiments.id", ondelete="CASCADE"))

    hypothesis_summary: Mapped[str] = mapped_column(String, nullable=False)
    baseline_variant_id: Mapped[str | None] = mapped_column(String, ForeignKey("experiment_variants.id"), nullable=True)
    candidate_variant_id: Mapped[str | None] = mapped_column(String, ForeignKey("experiment_variants.id"), nullable=True)

    changed_variables: Mapped[list[str]] = mapped_column(JSON, default=list)
    held_constant_variables: Mapped[list[str]] = mapped_column(JSON, default=list)
    workload: Mapped[str] = mapped_column(String, nullable=False)
    metrics_to_measure: Mapped[list[str]] = mapped_column(JSON, default=list)
    sample_size: Mapped[int] = mapped_column(Integer, default=100)
    stop_conditions: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_result: Mapped[str | None] = mapped_column(String, nullable=True)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="plan")
    baseline_variant: Mapped["ExperimentVariant"] = relationship("ExperimentVariant", foreign_keys=[baseline_variant_id])
    candidate_variant: Mapped["ExperimentVariant"] = relationship("ExperimentVariant", foreign_keys=[candidate_variant_id])


class ExperimentVariant(Base):
    __tablename__ = "experiment_variants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)

    # Flexible configuration for architecture/prompt changes
    system_configuration: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    hypothesis_id: Mapped[str | None] = mapped_column(String, ForeignKey("hypotheses.id", ondelete="SET NULL"), nullable=True)

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    experiment_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="draft")

    # Legacy fields kept for compatibility with Phase 2 frontend
    candidate_description: Mapped[str] = mapped_column(String, nullable=False)
    baseline_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    candidate_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    candidate_changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    sequence_number: Mapped[int] = mapped_column(Integer, default=1)

    conclusion: Mapped[str | None] = mapped_column(String, nullable=True)
    hypothesis_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    adopted: Mapped[bool] = mapped_column(Boolean, default=False)
    regression_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    strategy_reason: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="experiments")
    hypothesis: Mapped["Hypothesis"] = relationship("Hypothesis", back_populates="experiments")
    plan: Mapped["ExperimentPlan"] = relationship("ExperimentPlan", back_populates="experiment", uselist=False, cascade="all, delete-orphan")
    runs: Mapped[list["ExperimentRun"]] = relationship("ExperimentRun", back_populates="experiment", cascade="all, delete-orphan")
    evidence: Mapped[list["Evidence"]] = relationship("Evidence", back_populates="experiment", cascade="all, delete-orphan")
    decisions: Mapped[list["Decision"]] = relationship("Decision", back_populates="experiment", cascade="all, delete-orphan")
    session_id: Mapped[str | None] = mapped_column(String, ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=True)
    research_session: Mapped["ResearchSession"] = relationship("ResearchSession", foreign_keys=[session_id])


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = mapped_column(String, ForeignKey("experiments.id", ondelete="CASCADE"))
    variant_id: Mapped[str] = mapped_column(String, ForeignKey("experiment_variants.id"))

    status: Mapped[str] = mapped_column(String, default="pending")
    runner_type: Mapped[str] = mapped_column(String, nullable=False)
    execution_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    evaluation_tier: Mapped[str] = mapped_column(String, default="legacy_phase16")
    evaluation_policy_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    dataset_version: Mapped[str | None] = mapped_column(String, nullable=True)
    dataset_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    execution_provenance: Mapped[str | None] = mapped_column(String, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="runs")
    variant: Mapped["ExperimentVariant"] = relationship("ExperimentVariant")
    metric_results: Mapped[list["MetricResult"]] = relationship("MetricResult", back_populates="run", cascade="all, delete-orphan")
    trials: Mapped[list["ExperimentTrial"]] = relationship("ExperimentTrial", back_populates="run", cascade="all, delete-orphan")


class ExperimentTrial(Base):
    __tablename__ = "experiment_trials"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String, ForeignKey("experiment_runs.id", ondelete="CASCADE"))
    trial_index: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String, default="pending")
    error_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    execution_provenance: Mapped[str | None] = mapped_column(String, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["ExperimentRun"] = relationship("ExperimentRun", back_populates="trials")
    metric_results: Mapped[list["MetricResult"]] = relationship("MetricResult", back_populates="trial", cascade="all, delete-orphan")


class MetricResult(Base):
    __tablename__ = "metric_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String, ForeignKey("experiment_runs.id", ondelete="CASCADE"))
    trial_id: Mapped[str | None] = mapped_column(String, ForeignKey("experiment_trials.id", ondelete="CASCADE"), nullable=True)

    metric_name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False) # e.g. "synthetic", "nebius"

    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run: Mapped["ExperimentRun"] = relationship("ExperimentRun", back_populates="metric_results")
    trial: Mapped["ExperimentTrial"] = relationship("ExperimentTrial", back_populates="metric_results")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = mapped_column(String, ForeignKey("experiments.id", ondelete="CASCADE"))

    claim: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_values: Mapped[dict] = mapped_column(JSON, default=dict)
    candidate_values: Mapped[dict] = mapped_column(JSON, default=dict)
    calculations: Mapped[dict] = mapped_column(JSON, default=dict)
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="evidence")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = mapped_column(String, ForeignKey("experiments.id", ondelete="CASCADE"))

    result: Mapped[str] = mapped_column(String, nullable=False) # RETAIN, REJECT, INCONCLUSIVE
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    constraint_evaluations: Mapped[list[dict]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="decisions")


class ComparisonEvaluation(Base):
    __tablename__ = "comparison_evaluations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    baseline_run_id: Mapped[str] = mapped_column(String, ForeignKey("experiment_runs.id", ondelete="CASCADE"))
    candidate_run_id: Mapped[str] = mapped_column(String, ForeignKey("experiment_runs.id", ondelete="CASCADE"))

    policy_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    dataset_version: Mapped[str | None] = mapped_column(String, nullable=True)
    dataset_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    comparison_provenance: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    baseline_run: Mapped["ExperimentRun"] = relationship("ExperimentRun", foreign_keys=[baseline_run_id])
    candidate_run: Mapped["ExperimentRun"] = relationship("ExperimentRun", foreign_keys=[candidate_run_id])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "baseline_run" in kwargs and "candidate_run" in kwargs:
            base = kwargs["baseline_run"]
            cand = kwargs["candidate_run"]
            if base.evaluation_tier != cand.evaluation_tier:
                raise ValueError("Cannot compare runs with different evaluation tiers.")
            if base.dataset_version != cand.dataset_version:
                raise ValueError("Cannot compare runs with different dataset versions.")
            if base.dataset_hash != cand.dataset_hash:
                raise ValueError("Cannot compare runs with different dataset hashes.")
            if base.evaluation_policy_snapshot != cand.evaluation_policy_snapshot:
                raise ValueError("Cannot compare runs with different evaluation policies.")


class ExperimentEvent(Base):
    __tablename__ = "experiment_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id: Mapped[str] = mapped_column(String, ForeignKey("experiments.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    metadata_data: Mapped[dict] = mapped_column(JSON, default=dict)

class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id", ondelete="CASCADE"))

    status: Mapped[str] = mapped_column(String, default="created")
    termination_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    max_iterations: Mapped[int] = mapped_column(Integer, default=5)
    max_experiments: Mapped[int] = mapped_column(Integer, default=10)
    budget_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    iteration_count: Mapped[int] = mapped_column(Integer, default=0)
    experiment_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_experiment_count: Mapped[int] = mapped_column(Integer, default=0)

    current_best_experiment_id: Mapped[str | None] = mapped_column(String, ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True)
    current_best_variant_id: Mapped[str | None] = mapped_column(String, ForeignKey("experiment_variants.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped["Project"] = relationship("Project")
    best_experiment: Mapped["Experiment"] = relationship("Experiment", foreign_keys=[current_best_experiment_id])
    best_variant: Mapped["ExperimentVariant"] = relationship("ExperimentVariant", foreign_keys=[current_best_variant_id])
