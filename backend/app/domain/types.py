import enum
from pydantic import BaseModel
from typing import Any, Optional, Dict, List

class ExperimentState(str, enum.Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    MEASURING = "measuring"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class MetricDirection(str, enum.Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"

class DecisionResult(str, enum.Enum):
    RETAIN = "retain"
    REJECT = "reject"
    INCONCLUSIVE = "inconclusive"

class EvaluationTier(str, enum.Enum):
    LEGACY_PHASE16 = "legacy_phase16"
    OPTIMIZATION = "optimization"
    REGRESSION = "regression"
    HOLDOUT = "holdout"

class RunnerType(str, enum.Enum):
    SYNTHETIC = "synthetic"
    NEBIUS = "nebius"
    REAL_AI = "real_ai"

class ProvenanceType(str, enum.Enum):
    SIMULATION = "SIMULATION"
    REAL_EXECUTION = "REAL EXECUTION"
    UNKNOWN = "UNKNOWN / INVALID"

def classify_runner_provenance(runner_type: str) -> str:
    if not runner_type:
        return ProvenanceType.UNKNOWN.value
    rt = runner_type.lower()
    if rt == "synthetic":
        return ProvenanceType.SIMULATION.value
    elif rt in ("real_ai", "nebius"):
        return ProvenanceType.REAL_EXECUTION.value
    return ProvenanceType.UNKNOWN.value

class ConstraintOperator(str, enum.Enum):
    GTE = ">="
    LTE = "<="
    EQ = "=="
    GT = ">"
    LT = "<"

class ConstraintEvaluation(BaseModel):
    metric_name: str
    passed: bool
    missing_metric: bool
    actual_value: Optional[float] = None
    required_value: float
    operator: ConstraintOperator
    sample_size: int = 0
    evidence_valid: bool = True

class SessionState(str, enum.Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"

class StopReason(str, enum.Enum):
    OBJECTIVE_SATISFIED = "OBJECTIVE_SATISFIED"
    MAX_ITERATIONS = "MAX_ITERATIONS"
    MAX_EXPERIMENTS = "MAX_EXPERIMENTS"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    NO_VALID_CANDIDATE = "NO_VALID_CANDIDATE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    SEARCH_SPACE_EXHAUSTED = "SEARCH_SPACE_EXHAUSTED"
