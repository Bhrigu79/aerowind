from pydantic import BaseModel, Field, model_validator
from typing import Dict, Any

class EvaluationPolicy(BaseModel):
    min_trials: int = Field(default=1, description="Minimum number of trials to run")
    max_trials: int = Field(default=1, description="Maximum number of trials to run")
    alpha_level: float = Field(default=1.0, description="Required statistical confidence")
    mpe_thresholds: Dict[str, float] = Field(default_factory=dict, description="Minimum practical effects for metrics")
    failure_tolerance_ratio: float = Field(default=0.0, description="Allowed fraction of failed trials")
    require_comparative_improvement: bool = Field(default=False, description="Whether comparative improvement is required for adoption")
    required_comparative_metrics: list[str] = Field(default_factory=list, description="Specific metrics that MUST demonstrate comparative improvement if require_comparative_improvement is True")
    require_holdout_validation: bool = Field(default=False, description="Whether holdout validation is required")
    require_regression_validation: bool = Field(default=False, description="Whether regression validation is required")

    @model_validator(mode='after')
    def check_policy_bounds(self) -> 'EvaluationPolicy':
        if self.min_trials <= 0:
            raise ValueError("min_trials must be > 0")
        if self.max_trials <= 0:
            raise ValueError("max_trials must be > 0")
        if self.max_trials < self.min_trials:
            raise ValueError("max_trials must be >= min_trials")
        if not (0.0 <= self.failure_tolerance_ratio <= 1.0):
            raise ValueError("failure_tolerance_ratio must be between 0.0 and 1.0")
        return self

from enum import Enum
from typing import Optional, List

class MetricObservationSet(BaseModel):
    values: List[float]
    raw_observations: Optional[List[List[float]]] = None
    is_legacy: bool = False

class EvidenceStatus(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT_SAMPLES = "INSUFFICIENT_SAMPLES"
    INVALID_DATA = "INVALID_DATA"
    NO_OBSERVED_EFFECT = "NO_OBSERVED_EFFECT"
    BELOW_PRACTICAL_EFFECT = "BELOW_PRACTICAL_EFFECT"
    STATISTICALLY_SUPPORTED = "STATISTICALLY_SUPPORTED"
    NOT_STATISTICALLY_SUPPORTED = "NOT_STATISTICALLY_SUPPORTED"
    DEGENERATE_ZERO_VARIANCE = "DEGENERATE_ZERO_VARIANCE"
    LEGACY = "LEGACY"
    INSUFFICIENT_STATISTICAL_EVIDENCE = "INSUFFICIENT_STATISTICAL_EVIDENCE"

class MetricStatistics(BaseModel):
    n: int
    invalid_count: int = 0
    invalid_reason: Optional[str] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    variance: Optional[float] = None
    std_dev: Optional[float] = None
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    p50: Optional[float] = None
    p95: Optional[float] = None
    valid: bool = True
    is_legacy: bool = False

class StatisticalTestResult(BaseModel):
    absolute_difference: Optional[float] = None
    relative_difference: Optional[float] = None
    mpe: float = 0.0
    effect_above_mpe: Optional[bool] = None
    statistically_supported: Optional[bool] = None
    is_regression: bool = False
    significant_regression: bool = False
    test_statistic: Optional[float] = None
    degrees_of_freedom: Optional[float] = None
    p_value: Optional[float] = None
    confidence_interval_lower: Optional[float] = None
    confidence_interval_upper: Optional[float] = None
    status: EvidenceStatus

class ComparisonEvidence(BaseModel):
    baseline_stats: MetricStatistics
    candidate_stats: MetricStatistics
    comparison: StatisticalTestResult

class EvaluationTier(str, Enum):
    OPTIMIZATION = "OPTIMIZATION"
    REGRESSION = "REGRESSION"
    HOLDOUT = "HOLDOUT"
    LEGACY_PHASE16 = "LEGACY_PHASE16"

class DatasetIdentity(BaseModel):
    role: str
    version: str
    hash: str

class EvaluationEvidence(BaseModel):
    evaluation_tier: EvaluationTier
    dataset_identity: DatasetIdentity
    policy_snapshot: EvaluationPolicy
    experiment_id: str
    run_id: str
    metrics: Dict[str, ComparisonEvidence] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    is_successful: bool = True

    @property
    def optimization_visible(self) -> bool:
        return self.evaluation_tier == EvaluationTier.OPTIMIZATION
