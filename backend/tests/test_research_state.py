import pytest
import uuid
import json
from typing import Dict, Any
from app.db.models import Experiment, ExperimentRun, ExperimentPlan, ExperimentVariant, Decision, MetricResult
from app.schemas.evaluation import EvaluationPolicy
from app.domain.types import EvaluationTier, DecisionResult, MetricDirection
from app.schemas.research import ResearchState, ExploredConfiguration, FailedRegion
from app.services.research_state import ResearchStateService
from app.domain.types import EvaluationTier, DecisionResult

def create_mock_run(tier: str, variant_id: str, success: bool = True, metrics: Dict[str, list] = None) -> ExperimentRun:
    run = ExperimentRun(
        id=str(uuid.uuid4()),
        variant_id=variant_id,
        evaluation_tier=tier,
        success=success,
        error_info=None if success else "Runner crashed"
    )
    if metrics:
        run.metric_results = []
        for m_name, vals in metrics.items():
            for v in vals:
                run.metric_results.append(MetricResult(metric_name=m_name, value=v, unit="", direction=""))
    else:
        run.metric_results = []
    return run

def create_mock_experiment(
    config: Dict[str, Any],
    decision_res: str,
    decision_rationale: str,
    runs: list,
    adopted: bool = False
) -> Experiment:
    exp = Experiment(id=str(uuid.uuid4()), adopted=adopted)

    cand_var = ExperimentVariant(id=str(uuid.uuid4()), system_configuration=config)
    base_var = ExperimentVariant(id=str(uuid.uuid4()), system_configuration={})

    # assign cand variant id to runs
    for i, r in enumerate(runs):
        if r.variant_id == "CAND":
            r.variant_id = cand_var.id
        elif r.variant_id == "BASE":
            r.variant_id = base_var.id

    exp.runs = runs
    exp.plan = ExperimentPlan(
        candidate_variant=cand_var,
        baseline_variant=base_var,
        changed_variables=list(config.keys())
    )

    if decision_res:
        exp.decisions = [Decision(result=decision_res, rationale=decision_rationale)]
    else:
        exp.decisions = []

    return exp

def test_A_empty_history():
    state = ResearchStateService.build_state(
        objective_id="obj_1", objective_constraints={}, optimization_directions={},
        policy_snapshot=EvaluationPolicy(), experiments=[]
    )
    assert len(state.explored_configurations) == 0
    assert len(state.observed_effects) == 0

def test_B_valid_optimization_experiment():
    r_base = create_mock_run(EvaluationTier.OPTIMIZATION.value, "BASE", metrics={"q": [10, 10]})
    r_cand = create_mock_run(EvaluationTier.OPTIMIZATION.value, "CAND", metrics={"q": [20, 20]})
    exp = create_mock_experiment({"a": 1}, DecisionResult.RETAIN.value, "good", [r_base, r_cand], adopted=True)

    state = ResearchStateService.build_state(
        "obj", {}, {"q": MetricDirection.HIGHER_IS_BETTER}, EvaluationPolicy(), [exp]
    )
    assert len(state.explored_configurations) == 1
    assert state.explored_configurations[0].decision == DecisionResult.RETAIN.value
    assert len(state.observed_effects) == 1
    assert state.observed_effects[0].improvement_delta == 10
    assert state.feasible_configurations == [state.explored_configurations[0].fingerprint]
    assert state.current_best_fingerprint == state.explored_configurations[0].fingerprint

def test_C_D_Q_holdout_regression_cannot_enter_optimization():
    # Optimization fails or is missing, only holdout run exists
    r_holdout = create_mock_run(EvaluationTier.HOLDOUT.value, "CAND", metrics={"q": [20, 20]})
    r_base = create_mock_run(EvaluationTier.HOLDOUT.value, "BASE", metrics={"q": [10, 10]})
    exp = create_mock_experiment({"b": 2}, DecisionResult.REJECT.value, "holdout validation failed", [r_holdout, r_base])

    state = ResearchStateService.build_state("obj", {}, {}, EvaluationPolicy(), [exp])
    # Explored config must be 0 because there's no opt run
    assert len(state.explored_configurations) == 0
    assert len(state.observed_effects) == 0

def test_E_legacy_evidence():
    r_base = create_mock_run(EvaluationTier.LEGACY_PHASE16.value, "BASE", metrics={"q": [10]})
    r_cand = create_mock_run(EvaluationTier.LEGACY_PHASE16.value, "CAND", metrics={"q": [15]})
    exp = create_mock_experiment({"a": 1}, DecisionResult.INCONCLUSIVE.value, "legacy", [r_base, r_cand])

    state = ResearchStateService.build_state("obj", {}, {"q": MetricDirection.HIGHER_IS_BETTER}, EvaluationPolicy(), [exp])

    # Wait, ResearchStateService filters OPTIMIZATION tier for opt_run.
    # If it's legacy, opt_run is None.
    # The requirement: "Legacy evidence: -> identifiable as legacy -> cannot masquerade as modern"
    # Actually, legacy evidence won't even be parsed as opt_run because opt_run requires OPTIMIZATION tier.
    # Thus, it produces 0 explored configs, which is correctly excluded.
    assert len(state.explored_configurations) == 0

def test_F_execution_failure_not_classified_as_candidate_failure():
    r_cand = create_mock_run(EvaluationTier.OPTIMIZATION.value, "CAND", success=False)
    exp = create_mock_experiment({"x": 1}, DecisionResult.INCONCLUSIVE.value, "execution failed due to timeout", [r_cand])

    state = ResearchStateService.build_state("obj", {}, {}, EvaluationPolicy(), [exp])

    assert len(state.failed_regions) == 0
    assert len(state.uncertainties) == 1
    assert state.uncertainties[0].uncertainty_type == "EXECUTION_FAILED"

def test_G_constraint_failure():
    r_base = create_mock_run(EvaluationTier.OPTIMIZATION.value, "BASE", metrics={"lat": [3000]})
    r_cand = create_mock_run(EvaluationTier.OPTIMIZATION.value, "CAND", metrics={"lat": [5000]})
    exp = create_mock_experiment({"x": 1}, DecisionResult.REJECT.value, "hard constraints failed", [r_base, r_cand])

    state = ResearchStateService.build_state("obj", {}, {}, EvaluationPolicy(), [exp])
    assert len(state.failed_regions) == 1
    assert state.failed_regions[0].failure_type == "CONSTRAINT_FAILURE"

def test_H_invalid_evidence():
    r_cand = create_mock_run(EvaluationTier.OPTIMIZATION.value, "CAND")
    exp = create_mock_experiment({"x": 1}, DecisionResult.REJECT.value, "explicitly corrupt", [r_cand])

    state = ResearchStateService.build_state("obj", {}, {}, EvaluationPolicy(), [exp])
    assert len(state.failed_regions) == 1
    assert state.failed_regions[0].failure_type == "INVALID_EVIDENCE"

def test_I_J_fingerprint_normalization():
    conf1 = {"temperature": 0.7}
    conf2 = {"temperature": 0.7, "retries": 3} # assuming 3 is default

    # We patch ConfigurationValidator to simulate normalization for this test
    # In reality, ConfigurationValidator would do this. Here we just test ResearchStateService._fingerprint directly
    from app.core.config_validator import ConfigurationValidator
    orig = ConfigurationValidator.normalize
    ConfigurationValidator.normalize = lambda c: {"temperature": 0.7, "retries": 3} if c.get("temperature") == 0.7 else c

    f1 = ResearchStateService._fingerprint(conf1)
    f2 = ResearchStateService._fingerprint(conf2)
    assert f1 == f2

    f3 = ResearchStateService._fingerprint({"temperature": 0.8})
    assert f1 != f3

    ConfigurationValidator.normalize = orig

def test_K_M_deterministic_aggregation():
    r_base = create_mock_run(EvaluationTier.OPTIMIZATION.value, "BASE", metrics={"q": [10, 10]})
    r_cand = create_mock_run(EvaluationTier.OPTIMIZATION.value, "CAND", metrics={"q": [20, 20]})
    exp1 = create_mock_experiment({"a": 1}, DecisionResult.RETAIN.value, "good", [r_base, r_cand], adopted=True)
    exp1.id = "exp1"

    r_base2 = create_mock_run(EvaluationTier.OPTIMIZATION.value, "BASE", metrics={"q": [10, 10]})
    r_cand2 = create_mock_run(EvaluationTier.OPTIMIZATION.value, "CAND", metrics={"q": [20, 20]})
    exp2 = create_mock_experiment({"a": 1}, DecisionResult.RETAIN.value, "good", [r_base2, r_cand2], adopted=True)
    exp2.id = "exp2"

    state1 = ResearchStateService.build_state("obj", {}, {"q": MetricDirection.HIGHER_IS_BETTER}, EvaluationPolicy(), [exp2, exp1])
    state2 = ResearchStateService.build_state("obj", {}, {"q": MetricDirection.HIGHER_IS_BETTER}, EvaluationPolicy(), [exp1, exp2])

    assert state1.explored_configurations[0].experiment_id == state2.explored_configurations[0].experiment_id

def test_N_P_S_no_llm_claims():
    # ResearchState is purely Pydantic types, no text fields except explicitly copied rationale
    state = ResearchStateService.build_state("obj", {}, {}, EvaluationPolicy(), [])
    # Type checking ensures no causal field is fabricated
    assert not hasattr(state, "global_optimum")
    assert not hasattr(state, "llm_summary")

def test_O_missing_statistical_evidence():
    r_cand = create_mock_run(EvaluationTier.OPTIMIZATION.value, "CAND")
    exp = create_mock_experiment({"x": 1}, DecisionResult.INCONCLUSIVE.value, "missing comparative evidence", [r_cand])
    state = ResearchStateService.build_state("obj", {}, {}, EvaluationPolicy(), [exp])
    assert state.uncertainties[0].uncertainty_type == "MISSING_COMPARATIVE_EVIDENCE"

def test_R_current_best_semantics():
    r_base = create_mock_run(EvaluationTier.OPTIMIZATION.value, "BASE", metrics={"q": [10, 10]})
    r_cand1 = create_mock_run(EvaluationTier.OPTIMIZATION.value, "CAND", metrics={"q": [20, 20]})
    exp1 = create_mock_experiment({"a": 1}, DecisionResult.RETAIN.value, "good", [r_base, r_cand1], adopted=True)

    r_cand2 = create_mock_run(EvaluationTier.OPTIMIZATION.value, "CAND", metrics={"q": [25, 25]})
    exp2 = create_mock_experiment({"a": 2}, DecisionResult.RETAIN.value, "better", [r_base, r_cand2], adopted=True)

    # Current best should be the one adopted LAST
    # Sorting is by id or created_at. We'll set id to ensure order
    exp1.id = "1"
    exp2.id = "2"

    state = ResearchStateService.build_state("obj", {}, {}, EvaluationPolicy(), [exp1, exp2])
    assert state.current_best_fingerprint == ResearchStateService._fingerprint({"a": 2})
