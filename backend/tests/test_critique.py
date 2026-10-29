import pytest
import copy
from typing import List
from app.db.models import Experiment, ExperimentRun, ExperimentTrial, MetricResult
from app.schemas.research import (
    ResearchState, ExploredConfiguration, ObservedEffect, ParetoFrontier,
    ResearchCritique, CritiqueType, CritiqueStatus
)
from app.schemas.evaluation import EvaluationPolicy
from app.services.critique import SelfAdversarialCritiqueEngine
from app.domain.types import DecisionResult, MetricDirection, EvaluationTier

def create_mock_state() -> ResearchState:
    state = ResearchState(
        objective_id="obj_1",
        objective_constraints={},
        optimization_directions={},
        policy_snapshot=EvaluationPolicy(min_trials=3, max_trials=5, require_holdout_validation=False, require_regression_validation=False)
    )
    return state

def add_config(state: ResearchState, fp: str, decision: str = DecisionResult.RETAIN.value, provenance: str = "sys"):
    state.explored_configurations.append(ExploredConfiguration(
        canonical_configuration={"v": fp},
        fingerprint=fp,
        experiment_id=f"exp_{fp}",
        run_id=f"run_{fp}",
        decision=decision,
        changed_dimensions=["v"],
        dataset_version="v1",
        execution_provenance=provenance
    ))

def add_effect(state: ResearchState, fp: str, metric: str, sample_size: int = 3, mpe: bool = True, stat: bool = True):
    state.observed_effects.append(ObservedEffect(
        metric=metric,
        direction=MetricDirection.HIGHER_IS_BETTER,
        baseline_value=10.0,
        candidate_value=12.0,
        improvement_delta=2.0,
        effect_above_mpe=mpe,
        statistically_supported=stat,
        confidence_interval_lower=1.0,
        confidence_interval_upper=3.0,
        sample_size=sample_size,
        source_experiment_id=f"exp_{fp}",
        source_run_id=f"run_{fp}"
    ))

def create_experiment(fp: str, tier: str = EvaluationTier.OPTIMIZATION.value, success: bool = True, legacy: bool = False) -> Experiment:
    exp = Experiment(id=f"exp_{fp}", status="completed")
    run = ExperimentRun(id=f"run_{fp}", experiment_id=exp.id, evaluation_tier=tier, success=success)
    if legacy:
        metric = MetricResult(id=f"m_{fp}", run_id=run.id, trial_id=None, metric_name="cost", value=10.0, unit="ms", direction="LOWER_IS_BETTER", sample_size=1, source="sys")
        run.metric_results = [metric]
    exp.runs = [run]
    return exp

def test_A_B_sufficient_insufficient_trials():
    state = create_mock_state()
    add_config(state, "ok_fp")
    add_effect(state, "ok_fp", "cost", sample_size=3) # min is 3

    add_config(state, "bad_fp")
    add_effect(state, "bad_fp", "cost", sample_size=2)

    critiques = SelfAdversarialCritiqueEngine.evaluate(state)
    assert not any(c.target_id == "ok_fp" and c.critique_type == CritiqueType.INSUFFICIENT_TRIALS for c in critiques)
    assert any(c.critique_type == CritiqueType.INSUFFICIENT_TRIALS and "cost" in c.claim for c in critiques)

def test_C_D_weak_effect_and_stats():
    state = create_mock_state()
    add_config(state, "fp_1")
    add_effect(state, "fp_1", "q1", mpe=False, stat=True)
    add_effect(state, "fp_1", "q2", mpe=True, stat=False)

    critiques = SelfAdversarialCritiqueEngine.evaluate(state)
    types = [c.critique_type for c in critiques]
    assert CritiqueType.WEAK_EFFECT in types
    assert CritiqueType.SIGNIFICANCE_NOT_ESTABLISHED in types

def test_E_F_missing_validation():
    state = create_mock_state()
    state.policy_snapshot.require_holdout_validation = True
    state.policy_snapshot.require_regression_validation = True
    add_config(state, "fp_1")
    add_effect(state, "fp_1", "q")

    # Missing runs entirely
    critiques = SelfAdversarialCritiqueEngine.evaluate(state, experiments=[create_experiment("fp_1")])
    types = [c.critique_type for c in critiques]
    assert CritiqueType.GENERALIZATION_UNVERIFIED in types
    assert CritiqueType.REGRESSION_UNVERIFIED in types

def test_G_search_exhaustion():
    state = create_mock_state()
    critiques = SelfAdversarialCritiqueEngine.evaluate(state, search_exhausted=True)
    assert any(c.critique_type == CritiqueType.SEARCH_COVERAGE_LIMITED for c in critiques)

def test_H_dominated_best():
    state = create_mock_state()
    add_config(state, "fp_1")
    pf = ParetoFrontier(
        objective_id="obj_1",
        frontier_fingerprints=["fp_2"],
        current_best_fingerprint="fp_1",
        current_best_is_dominated=True
    )
    critiques = SelfAdversarialCritiqueEngine.evaluate(state, pareto_frontier=pf)
    assert any(c.critique_type == CritiqueType.DOMINATED_CURRENT_BEST for c in critiques)

def test_I_J_legacy_and_provenance():
    state = create_mock_state()
    add_config(state, "fp_1", provenance="") # missing provenance
    exp = create_experiment("fp_1", legacy=True) # legacy metrics

    critiques = SelfAdversarialCritiqueEngine.evaluate(state, experiments=[exp])
    types = [c.critique_type for c in critiques]
    assert CritiqueType.LEGACY_EVIDENCE in types
    assert CritiqueType.MISSING_PROVENANCE in types

def test_L_M_N_O_no_decision_override():
    # Critiques shouldn't change the base objects
    state = create_mock_state()
    add_config(state, "fp_1", decision=DecisionResult.RETAIN.value)
    add_effect(state, "fp_1", "q", stat=False)

    state_copy = copy.deepcopy(state)
    critiques = SelfAdversarialCritiqueEngine.evaluate(state)

    # State must be exactly identical
    assert state.explored_configurations[0].decision == DecisionResult.RETAIN.value
    assert state.explored_configurations[0].decision == state_copy.explored_configurations[0].decision

def test_R_S_T_determinism_and_immutability():
    state = create_mock_state()
    add_config(state, "fp_2")
    add_effect(state, "fp_2", "q", mpe=False)
    add_config(state, "fp_1")
    add_effect(state, "fp_1", "q", mpe=False)

    c1 = SelfAdversarialCritiqueEngine.evaluate(state)

    state.explored_configurations.reverse()
    state.observed_effects.reverse()

    c2 = SelfAdversarialCritiqueEngine.evaluate(state)

    assert [c.critique_id for c in c1] == [c.critique_id for c in c2]
    # No duplicate critiques for the same target and type
    assert len(c1) == len(set(c.critique_id for c in c1))

def test_U_V_evidence_refs():
    state = create_mock_state()
    add_config(state, "fp_1")
    add_effect(state, "fp_1", "q", stat=False)

    critiques = SelfAdversarialCritiqueEngine.evaluate(state)
    for c in critiques:
        assert c.status == CritiqueStatus.VERIFIED
        assert len(c.evidence_refs) > 0
