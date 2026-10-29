from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class PlannerStrategySchema(BaseModel):
    focus_area: str
    reason: str

class HypothesisSchema(BaseModel):
    claim: str
    expected_effect: str
    target_metric: str
    expected_direction: str
    expected_magnitude: float
    confidence: float
    independent_variable: str
    control_description: str
    candidate_description: str
    risks: str

class ExperimentPlanSchema(BaseModel):
    hypothesis_summary: str
    changed_variables: List[str]
    held_constant_variables: List[str]
    workload: str
    metrics_to_measure: List[str]
    sample_size: int
    stop_conditions: List[str]
    expected_result: str
    candidate_configuration: Dict[str, Any]

from app.schemas.evaluation import EvaluationPolicy
from app.domain.types import MetricDirection

class ObservedEffect(BaseModel):
    metric: str
    direction: MetricDirection
    baseline_value: Optional[float]
    candidate_value: Optional[float]
    improvement_delta: Optional[float]
    effect_above_mpe: bool
    statistically_supported: Optional[bool]
    confidence_interval_lower: Optional[float]
    confidence_interval_upper: Optional[float]
    sample_size: int
    source_experiment_id: str
    source_run_id: str

class ExploredConfiguration(BaseModel):
    canonical_configuration: Dict[str, Any]
    fingerprint: str
    experiment_id: str
    run_id: str
    decision: str  # RETAIN, REJECT, INCONCLUSIVE
    changed_dimensions: List[str]
    dataset_version: Optional[str]
    execution_provenance: Optional[str]

class FailedRegion(BaseModel):
    canonical_configuration: Dict[str, Any]
    fingerprint: str
    failure_type: str  # CONSTRAINT_FAILURE, COMPARATIVE_FAILURE, GENERALIZATION_FAILURE, EXECUTION_FAILURE, INVALID_EVIDENCE
    reason: str
    experiment_id: str
    run_id: str

class ResearchUncertainty(BaseModel):
    fingerprint: str
    uncertainty_type: str  # INSUFFICIENT_TRIALS, MISSING_COMPARATIVE_EVIDENCE, MISSING_GENERALIZATION_EVIDENCE, UNSUPPORTED_STATISTICAL_COMPARISON, EXECUTION_FAILED
    reason: str
    experiment_id: str
    run_id: str

class ResearchState(BaseModel):
    objective_id: str
    objective_constraints: Dict[str, float]
    optimization_directions: Dict[str, MetricDirection]
    policy_snapshot: EvaluationPolicy

    explored_configurations: List[ExploredConfiguration] = []
    observed_effects: List[ObservedEffect] = []
    failed_regions: List[FailedRegion] = []
    uncertainties: List[ResearchUncertainty] = []

    feasible_configurations: List[str] = [] # fingerprints of retained configs
    current_best_fingerprint: Optional[str] = None

class ParetoFrontier(BaseModel):
    objective_metrics: List[str] = []
    optimization_directions: Dict[str, MetricDirection] = {}

    frontier_fingerprints: List[str] = []
    dominated_fingerprints: List[str] = []
    dominance_relationships: Dict[str, List[str]] = {}

    metric_values: Dict[str, Dict[str, float]] = {}
    source_experiment_ids: Dict[str, str] = {}
    source_run_ids: Dict[str, str] = {}

    current_best_fingerprint: Optional[str] = None
    current_best_is_dominated: Optional[bool] = None

class FailureAtlasEntry(BaseModel):
    canonical_configuration: Dict[str, Any]
    fingerprint: str
    experiment_id: str
    run_id: str
    failure_type: str  # CONSTRAINT_FAILURE, COMPARATIVE_FAILURE, GENERALIZATION_FAILURE, INVALID_EVIDENCE
    reason: str
    failed_metrics: List[str] = []
    failed_constraints: List[str] = []
    observed_metric_values: Dict[str, float] = {}
    policy_snapshot: EvaluationPolicy
    dataset_version: Optional[str] = None
    execution_provenance: Optional[str] = None

class FailureAtlas(BaseModel):
    entries: List[FailureAtlasEntry] = []

from enum import Enum

class EvidenceNodeType(str, Enum):
    OBJECTIVE = "OBJECTIVE"
    HYPOTHESIS = "HYPOTHESIS"
    STRATEGY = "STRATEGY"
    CONFIGURATION = "CONFIGURATION"
    EXPERIMENT = "EXPERIMENT"
    EXPERIMENT_RUN = "EXPERIMENT_RUN"
    TRIAL = "TRIAL"
    METRIC_RESULT = "METRIC_RESULT"
    COMPARISON_EVALUATION = "COMPARISON_EVALUATION"
    DECISION = "DECISION"
    EVIDENCE_CERTIFICATE = "EVIDENCE_CERTIFICATE"
    FAILURE_ATLAS_ENTRY = "FAILURE_ATLAS_ENTRY"
    PARETO_FRONTIER = "PARETO_FRONTIER"
    RESEARCH_STATE = "RESEARCH_STATE"

class EvidenceEdgeType(str, Enum):
    MOTIVATED = "MOTIVATED"
    USES_STRATEGY = "USES_STRATEGY"
    TESTED = "TESTED"
    HAS_RUN = "HAS_RUN"
    HAS_TRIAL = "HAS_TRIAL"
    PRODUCED_METRIC = "PRODUCED_METRIC"
    PRODUCED_EVALUATION = "PRODUCED_EVALUATION"
    RESULTED_IN = "RESULTED_IN"
    PRODUCED = "PRODUCED"
    HAS_FAILURE_EVIDENCE = "HAS_FAILURE_EVIDENCE"
    MEMBER_OF = "MEMBER_OF"
    DERIVED_FROM = "DERIVED_FROM"

class EvidenceNode(BaseModel):
    node_id: str
    node_type: EvidenceNodeType
    source_id: str
    metadata_info: Dict[str, Any] = {}

class EvidenceEdge(BaseModel):
    source_node_id: str
    target_node_id: str
    relation_type: EvidenceEdgeType
    provenance: Optional[str] = None

class EvidenceGraph(BaseModel):
    nodes: List[EvidenceNode] = []
    edges: List[EvidenceEdge] = []
    schema_version: str = "1.0"

class CritiqueType(str, Enum):
    INSUFFICIENT_TRIALS = "INSUFFICIENT_TRIALS"
    HIGH_VARIANCE = "HIGH_VARIANCE"
    WEAK_EFFECT = "WEAK_EFFECT"
    SIGNIFICANCE_NOT_ESTABLISHED = "SIGNIFICANCE_NOT_ESTABLISHED"
    CONSTRAINT_MARGIN_TOO_SMALL = "CONSTRAINT_MARGIN_TOO_SMALL"
    GENERALIZATION_UNVERIFIED = "GENERALIZATION_UNVERIFIED"
    REGRESSION_UNVERIFIED = "REGRESSION_UNVERIFIED"
    SEARCH_COVERAGE_LIMITED = "SEARCH_COVERAGE_LIMITED"
    FAILURE_REGION_UNDEREXPLORED = "FAILURE_REGION_UNDEREXPLORED"
    DOMINATED_CURRENT_BEST = "DOMINATED_CURRENT_BEST"
    LEGACY_EVIDENCE = "LEGACY_EVIDENCE"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"

class CritiqueStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class ResearchCritique(BaseModel):
    critique_id: str
    target_type: str
    target_id: str
    critique_type: CritiqueType
    severity: str
    claim: str
    evidence_refs: List[str]
    status: CritiqueStatus
    deterministic_reason: str

class ReplayIntegrityStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    INTEGRITY_MISMATCH = "INTEGRITY_MISMATCH"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"

class ReplayEvent(BaseModel):
    event_id: str
    timestamp: datetime
    event_type: str
    description: str
    source_artifacts: List[str]

class ReplayLimitation(BaseModel):
    limitation_type: str
    description: str
    affected_artifacts: List[str]

class ResearchReplay(BaseModel):
    replay_id: str
    session_id: str
    status: ReplayIntegrityStatus
    objective_snapshot: Dict[str, Any]
    policy_snapshot: EvaluationPolicy
    timeline: List[ReplayEvent] = []

    # Reconstructed objects
    experiments: List[Dict[str, Any]] = []
    evaluations: List[Dict[str, Any]] = []

    # Projections
    research_state_snapshot: ResearchState
    critiques: List[ResearchCritique] = []
    limitations: List[ReplayLimitation] = []
