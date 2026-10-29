import pytest
import math
import copy
from app.schemas.research import (
    ResearchState, FailedRegion, ExploredConfiguration, ObservedEffect
)
from app.schemas.evaluation import EvaluationPolicy
from app.domain.types import MetricDirection
from app.services.failure_atlas import FailureAtlasService

def make_dummy_state() -> ResearchState:
    return ResearchState(
        objective_id="obj_1",
        objective_constraints={"cost": 50.0},
        optimization_directions={"quality": MetricDirection.HIGHER_IS_BETTER, "cost": MetricDirection.LOWER_IS_BETTER},
        policy_snapshot=EvaluationPolicy()
    )

def add_explored(state: ResearchState, run_id: str, decision: str, config_val: str):
    fp = f'{{"val": "{config_val}"}}'
    state.explored_configurations.append(ExploredConfiguration(
        canonical_configuration={"val": config_val},
        fingerprint=fp,
        experiment_id=f"exp_{run_id}",
        run_id=run_id,
        decision=decision,
        changed_dimensions=["val"],
        dataset_version="v1",
        execution_provenance="pytest"
    ))
    return fp

def add_failed_region(state: ResearchState, run_id: str, fp: str, config_val: str, failure_type: str, reason: str):
    state.failed_regions.append(FailedRegion(
        canonical_configuration={"val": config_val},
        fingerprint=fp,
        failure_type=failure_type,
        reason=reason,
        experiment_id=f"exp_{run_id}",
        run_id=run_id
    ))

def add_effect(state: ResearchState, run_id: str, metric: str, candidate_val: float, baseline_val: float = None, stat_sup: bool = False):
    state.observed_effects.append(ObservedEffect(
        metric=metric,
        direction=MetricDirection.HIGHER_IS_BETTER,
        baseline_value=baseline_val,
        candidate_value=candidate_val,
        improvement_delta=0.0,
        effect_above_mpe=False,
        statistically_supported=stat_sup,
        confidence_interval_lower=0.0,
        confidence_interval_upper=0.0,
        sample_size=10,
        source_experiment_id=f"exp_{run_id}",
        source_run_id=run_id
    ))


def test_A_exact_constraint_failure():
    state = make_dummy_state()
    fp = add_explored(state, "r1", "REJECT", "v1")
    add_failed_region(state, "r1", fp, "v1", "CONSTRAINT_FAILURE", "cost failed")
    add_effect(state, "r1", "cost", 100.0) # constraint is 50.0

    atlas = FailureAtlasService.build_atlas(state)
    assert len(atlas.entries) == 1
    assert atlas.entries[0].failure_type == "CONSTRAINT_FAILURE"
    assert "cost" in atlas.entries[0].failed_constraints

def test_B_comparative_failure():
    state = make_dummy_state()
    fp = add_explored(state, "r1", "REJECT", "v1")
    add_failed_region(state, "r1", fp, "v1", "COMPARATIVE_FAILURE", "regressed")
    add_effect(state, "r1", "quality", 10.0, baseline_val=20.0, stat_sup=True)

    atlas = FailureAtlasService.build_atlas(state)
    assert len(atlas.entries) == 1
    assert atlas.entries[0].failure_type == "COMPARATIVE_FAILURE"
    assert "quality" in atlas.entries[0].failed_metrics

def test_D_invalid_evidence():
    state = make_dummy_state()
    fp = add_explored(state, "r1", "REJECT", "v1")
    add_failed_region(state, "r1", fp, "v1", "INVALID_EVIDENCE", "corrupt")

    atlas = FailureAtlasService.build_atlas(state)
    assert len(atlas.entries) == 1
    assert atlas.entries[0].failure_type == "INVALID_EVIDENCE"

def test_E_F_execution_failure_missing_evidence():
    state = make_dummy_state()
    fp = add_explored(state, "r1", "INCONCLUSIVE", "v1")
    # execution failures or missing evidence result in INCONCLUSIVE and go to uncertainties, NOT failed_regions

    atlas = FailureAtlasService.build_atlas(state)
    assert len(atlas.entries) == 0

def test_H_I_J_duplicate_collapse_and_determinism():
    state = make_dummy_state()
    fp = add_explored(state, "r2", "REJECT", "v1")
    add_failed_region(state, "r2", fp, "v1", "CONSTRAINT_FAILURE", "fail 2")

    fp2 = add_explored(state, "r1", "REJECT", "v1")
    add_failed_region(state, "r1", fp2, "v1", "CONSTRAINT_FAILURE", "fail 1")

    # same canonical config, different runs. Should collapse deterministically to r1 (lexicographical)
    atlas = FailureAtlasService.build_atlas(state)
    assert len(atlas.entries) == 1
    assert atlas.entries[0].run_id == "r1"

def test_L_no_state_mutation():
    state = make_dummy_state()
    fp = add_explored(state, "r1", "REJECT", "v1")
    add_failed_region(state, "r1", fp, "v1", "CONSTRAINT_FAILURE", "cost failed")
    state_copy = copy.deepcopy(state)

    FailureAtlasService.build_atlas(state)
    assert len(state.failed_regions) == len(state_copy.failed_regions)

def test_M_R_nan_infinity():
    state = make_dummy_state()
    fp = add_explored(state, "r1", "REJECT", "v1")
    add_failed_region(state, "r1", fp, "v1", "CONSTRAINT_FAILURE", "bad math")
    add_effect(state, "r1", "cost", math.nan)
    add_effect(state, "r1", "quality", math.inf)

    atlas = FailureAtlasService.build_atlas(state)
    assert len(atlas.entries) == 1
    assert "cost" not in atlas.entries[0].observed_metric_values
    assert "quality" not in atlas.entries[0].observed_metric_values

def test_N_O_retrieval_and_canonical_fingerprint():
    state = make_dummy_state()
    fp = add_explored(state, "r1", "REJECT", "v1")
    add_failed_region(state, "r1", fp, "v1", "CONSTRAINT_FAILURE", "cost failed")

    atlas = FailureAtlasService.build_atlas(state)
    assert atlas.entries[0].fingerprint == fp

    retrieved = [e for e in atlas.entries if e.fingerprint == fp]
    assert len(retrieved) == 1
