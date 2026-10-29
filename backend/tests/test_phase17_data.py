import pytest
from app.db.models import ExperimentRun, ExperimentTrial, ComparisonEvaluation, Project, Experiment, ExperimentVariant
from app.domain.types import EvaluationTier
from app.schemas.evaluation import EvaluationPolicy
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

def test_evaluation_policy_schema():
    policy = EvaluationPolicy(min_trials=3, max_trials=10, alpha_level=0.05)
    assert policy.min_trials == 3
    assert policy.alpha_level == 0.05
    assert not policy.require_comparative_improvement
    assert policy.failure_tolerance_ratio == 0.0

def test_experiment_run_evaluation_tier():
    run = ExperimentRun(evaluation_tier=EvaluationTier.OPTIMIZATION.value, runner_type="synthetic")
    assert run.evaluation_tier == "optimization"

def test_experiment_trial_attributes():
    run = ExperimentRun(id="run1", evaluation_tier=EvaluationTier.OPTIMIZATION.value, runner_type="synthetic")
    trial = ExperimentTrial(run=run, trial_index=1, status="success", execution_provenance="synthetic")
    assert trial.run == run
    assert trial.trial_index == 1
    assert trial.execution_provenance == "synthetic"

def test_comparison_evaluation_attributes():
    base_run = ExperimentRun(
        id="base",
        evaluation_tier=EvaluationTier.OPTIMIZATION.value,
        runner_type="synthetic",
        dataset_version="v1",
        dataset_hash="hash1",
        evaluation_policy_snapshot={"min_trials": 3}
    )
    cand_run = ExperimentRun(
        id="cand",
        evaluation_tier=EvaluationTier.OPTIMIZATION.value,
        runner_type="synthetic",
        dataset_version="v1",
        dataset_hash="hash1",
        evaluation_policy_snapshot={"min_trials": 3}
    )
    comp = ComparisonEvaluation(
        baseline_run=base_run,
        candidate_run=cand_run,
        policy_snapshot={"min_trials": 3},
        dataset_hash="hash1"
    )
    assert comp.baseline_run == base_run
    assert comp.candidate_run == cand_run
    assert comp.policy_snapshot["min_trials"] == 3
    assert comp.dataset_hash == "hash1"

def test_comparison_evaluation_incompatible_runs():
    base_run = ExperimentRun(id="base", evaluation_tier=EvaluationTier.OPTIMIZATION.value, dataset_version="v1", dataset_hash="hash1", evaluation_policy_snapshot={"min_trials": 3})
    cand_run_diff_tier = ExperimentRun(id="cand1", evaluation_tier=EvaluationTier.REGRESSION.value, dataset_version="v1", dataset_hash="hash1", evaluation_policy_snapshot={"min_trials": 3})
    cand_run_diff_version = ExperimentRun(id="cand2", evaluation_tier=EvaluationTier.OPTIMIZATION.value, dataset_version="v2", dataset_hash="hash1", evaluation_policy_snapshot={"min_trials": 3})
    cand_run_diff_hash = ExperimentRun(id="cand3", evaluation_tier=EvaluationTier.OPTIMIZATION.value, dataset_version="v1", dataset_hash="hash2", evaluation_policy_snapshot={"min_trials": 3})
    cand_run_diff_policy = ExperimentRun(id="cand4", evaluation_tier=EvaluationTier.OPTIMIZATION.value, dataset_version="v1", dataset_hash="hash1", evaluation_policy_snapshot={"min_trials": 5})

    with pytest.raises(ValueError, match="Cannot compare runs with different evaluation tiers."):
        ComparisonEvaluation(baseline_run=base_run, candidate_run=cand_run_diff_tier)

    with pytest.raises(ValueError, match="Cannot compare runs with different dataset versions."):
        ComparisonEvaluation(baseline_run=base_run, candidate_run=cand_run_diff_version)

    with pytest.raises(ValueError, match="Cannot compare runs with different dataset hashes."):
        ComparisonEvaluation(baseline_run=base_run, candidate_run=cand_run_diff_hash)

    with pytest.raises(ValueError, match="Cannot compare runs with different evaluation policies."):
        ComparisonEvaluation(baseline_run=base_run, candidate_run=cand_run_diff_policy)
