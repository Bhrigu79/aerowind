import pytest
from datetime import datetime, timedelta
import copy

from app.db.models import (
    Experiment, ExperimentRun, ExperimentTrial, MetricResult,
    Decision, ComparisonEvaluation, Evidence, ExperimentPlan, ExperimentVariant
)
from app.schemas.research import (
    ResearchState, ExploredConfiguration, ReplayIntegrityStatus, ResearchReplay, CritiqueType, CritiqueStatus
)
from app.schemas.evaluation import EvaluationPolicy
from app.services.replay import ResearchReplayService
from app.domain.types import DecisionResult, MetricDirection, EvaluationTier
from app.core.config_validator import ConfigurationValidator

def create_mock_experiment(exp_id: str, config_val: str, created_at: datetime = None) -> Experiment:
    exp = Experiment(
        id=exp_id, status="completed", name=exp_id, experiment_type="opt",
        candidate_description="desc", created_at=created_at or datetime.utcnow()
    )
    var = ExperimentVariant(id=f"var_{exp_id}", system_configuration={"v": config_val})
    exp.plan = ExperimentPlan(id=f"plan_{exp_id}", candidate_variant=var, hypothesis_summary="h", workload="w")
    exp.runs = []
    exp.decisions = []
    exp.evidence = []
    return exp

def add_run_and_trial(exp: Experiment, tier: str, success: bool = True, t_offset: int = 0, legacy: bool = False) -> ExperimentRun:
    t = exp.created_at + timedelta(seconds=t_offset)
    run = ExperimentRun(id=f"run_{exp.id}_{tier}_{t_offset}", experiment_id=exp.id, variant_id=exp.plan.candidate_variant.id, evaluation_tier=tier, success=success, started_at=t)
    trial = ExperimentTrial(id=f"trial_{run.id}", run_id=run.id, trial_index=1, status="completed", completed_at=t+timedelta(seconds=1))

    metric = MetricResult(id=f"m_{trial.id}", run_id=run.id, trial_id=None if legacy else trial.id, metric_name="cost", value=10.0, unit="ms", direction="LOWER_IS_BETTER", sample_size=1, source="sys", timestamp=t+timedelta(seconds=2))
    run.trials = [trial]
    run.metric_results = [metric]
    exp.runs.append(run)
    return run

def test_A_B_AB_history_status():
    policy = EvaluationPolicy()

    # B. empty/missing session
    replay_empty = ResearchReplayService.build_replay("sess_1", [], [], None, policy, {"id": "obj_1"})
    assert replay_empty.status == ReplayIntegrityStatus.INSUFFICIENT_HISTORY
    assert len(replay_empty.timeline) == 0

    # A. complete session replay
    t = datetime(2025,1,1)
    exp = create_mock_experiment("exp_1", "v1", created_at=t)
    add_run_and_trial(exp, EvaluationTier.OPTIMIZATION.value)

    replay = ResearchReplayService.build_replay("sess_1", [exp], [], None, policy, {"id": "obj_1"})
    assert replay.status == ReplayIntegrityStatus.VERIFIED
    event_types = [e.event_type for e in replay.timeline]
    assert "EXPERIMENT_CREATED" in event_types
    assert "RUN_STARTED" in event_types
    assert "TRIAL_COMPLETED" in event_types
    assert "METRIC_RECORDED" in event_types

def test_C_D_Y_determinism():
    policy = EvaluationPolicy()
    t = datetime(2025, 1, 1)
    exp1 = create_mock_experiment("exp_1", "v1", created_at=t)
    exp2 = create_mock_experiment("exp_2", "v2", created_at=t+timedelta(minutes=1))

    r1 = ResearchReplayService.build_replay("sess", [exp1, exp2], [], None, policy, {})
    r2 = ResearchReplayService.build_replay("sess", [exp2, exp1], [], None, policy, {})

    assert r1.replay_id == r2.replay_id
    assert [e.event_id for e in r1.timeline] == [e.event_id for e in r2.timeline]

def test_E_F_G_H_I_K_exact_reconstruction():
    policy = EvaluationPolicy()
    exp = create_mock_experiment("exp_1", "v1")
    run = add_run_and_trial(exp, EvaluationTier.OPTIMIZATION.value, legacy=True)

    replay = ResearchReplayService.build_replay("sess", [exp], [], None, policy, {})
    # Legacy metric detection -> PARTIALLY_VERIFIED
    assert replay.status == ReplayIntegrityStatus.PARTIALLY_VERIFIED

    recon_exp = replay.experiments[0]
    assert recon_exp["experiment_id"] == "exp_1"
    import json
    assert recon_exp["configuration_fingerprint"] == json.dumps(ConfigurationValidator.normalize({"v": "v1"}), sort_keys=True)
    assert recon_exp["runs"][0]["run_id"] == run.id
    # Trial without metrics because legacy metric lacked trial_id
    assert len(recon_exp["runs"][0]["trials"][0]["metrics"]) == 0
    assert len(recon_exp["runs"][0]["legacy_metrics"]) == 1

def test_M_N_O_integrity_mismatch():
    policy = EvaluationPolicy()
    exp = create_mock_experiment("exp_1", "v1")
    add_run_and_trial(exp, EvaluationTier.OPTIMIZATION.value)

    # We create a recorded state that contradicts the deterministic one
    recorded_state = ResearchState(
        objective_id="unk",
        objective_constraints={},
        optimization_directions={},
        policy_snapshot=policy,
        explored_configurations=[ExploredConfiguration(
            canonical_configuration={"v": "v1"},
            fingerprint="wrong_fp",
            experiment_id="exp_1",
            run_id="run_1",
            decision=DecisionResult.RETAIN.value,
            changed_dimensions=[],
            dataset_version=None,
            execution_provenance=None
        )]
    )

    replay = ResearchReplayService.build_replay("sess", [exp], [], recorded_state, policy, {})
    assert replay.status == ReplayIntegrityStatus.INTEGRITY_MISMATCH
    # Must preserve historical truth rather than rewriting it!
    assert replay.research_state_snapshot.explored_configurations[0].fingerprint == "wrong_fp"

def test_T_evaluation_tier_separation():
    policy = EvaluationPolicy()
    exp = create_mock_experiment("exp_1", "v1")
    add_run_and_trial(exp, EvaluationTier.OPTIMIZATION.value)
    add_run_and_trial(exp, EvaluationTier.HOLDOUT.value)
    add_run_and_trial(exp, EvaluationTier.REGRESSION.value)

    replay = ResearchReplayService.build_replay("sess", [exp], [], None, policy, {})
    tiers = [r["tier"] for r in replay.experiments[0]["runs"]]
    assert EvaluationTier.OPTIMIZATION.value in tiers
    assert EvaluationTier.HOLDOUT.value in tiers
    assert EvaluationTier.REGRESSION.value in tiers

def test_S_critique_replay_distinction():
    policy = EvaluationPolicy()
    exp = create_mock_experiment("exp_1", "v1")
    add_run_and_trial(exp, EvaluationTier.OPTIMIZATION.value)

    replay = ResearchReplayService.build_replay("sess", [exp], [], None, policy, {})
    for c in replay.critiques:
        # Must be explicitly marked as derived
        assert "[REPLAY_DERIVED]" in c.claim

def test_AC_source_objects_unchanged():
    policy = EvaluationPolicy()
    exp = create_mock_experiment("exp_1", "v1")
    add_run_and_trial(exp, EvaluationTier.OPTIMIZATION.value)

    exp_copy = copy.deepcopy(exp)
    ResearchReplayService.build_replay("sess", [exp], [], None, policy, {})

    assert exp.id == exp_copy.id
    assert exp.runs[0].id == exp_copy.runs[0].id
