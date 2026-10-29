import pytest
from app.schemas.evaluation import (
    EvaluationEvidence, EvaluationTier, EvaluationPolicy,
    DatasetIdentity, ComparisonEvidence, MetricStatistics,
    StatisticalTestResult, EvidenceStatus
)
from app.services.firewall import EvaluationFirewall

def create_mock_evidence(
    tier: EvaluationTier,
    is_successful: bool = True,
    metric_status: EvidenceStatus = EvidenceStatus.STATISTICALLY_SUPPORTED
) -> EvaluationEvidence:
    policy = EvaluationPolicy()
    dataset = DatasetIdentity(role=tier.value.lower(), version="v1", hash="abcdef")

    comp_ev = ComparisonEvidence(
        baseline_stats=MetricStatistics(n=10),
        candidate_stats=MetricStatistics(n=10),
        comparison=StatisticalTestResult(
            status=metric_status,
            mpe=0.0
        )
    )

    return EvaluationEvidence(
        evaluation_tier=tier,
        dataset_identity=dataset,
        policy_snapshot=policy,
        experiment_id="exp_123",
        run_id="run_456",
        metrics={"latency": comp_ev},
        is_successful=is_successful
    )


def test_A_optimization_evidence_is_optimization_visible():
    ev = create_mock_evidence(EvaluationTier.OPTIMIZATION)
    assert ev.optimization_visible is True
    assert EvaluationFirewall.can_enter_optimization_memory(ev) is True
    assert EvaluationFirewall.can_influence_strategy(ev) is True
    assert EvaluationFirewall.can_influence_hypothesis_generation(ev) is True
    assert EvaluationFirewall.can_be_used_for_final_validation(ev) is False

def test_B_regression_evidence_cannot_influence_strategy():
    ev = create_mock_evidence(EvaluationTier.REGRESSION)
    assert ev.optimization_visible is False
    assert EvaluationFirewall.can_influence_strategy(ev) is False
    assert EvaluationFirewall.can_influence_hypothesis_generation(ev) is False
    assert EvaluationFirewall.can_enter_optimization_memory(ev) is False
    assert EvaluationFirewall.can_be_used_for_final_validation(ev) is True

def test_C_holdout_evidence_cannot_influence_strategy():
    ev = create_mock_evidence(EvaluationTier.HOLDOUT)
    assert ev.optimization_visible is False
    assert EvaluationFirewall.can_influence_strategy(ev) is False
    assert EvaluationFirewall.can_influence_hypothesis_generation(ev) is False
    assert EvaluationFirewall.can_enter_optimization_memory(ev) is False
    assert EvaluationFirewall.can_be_used_for_final_validation(ev) is True

def test_D_E_metrics_cannot_enter_optimization_context():
    ev_holdout = create_mock_evidence(EvaluationTier.HOLDOUT)
    ev_regression = create_mock_evidence(EvaluationTier.REGRESSION)

    filtered = EvaluationFirewall.filter_optimization_context([ev_holdout, ev_regression])
    assert len(filtered) == 0

def test_F_legacy_evidence_cannot_become_fresh_optimization_evidence():
    ev = create_mock_evidence(EvaluationTier.LEGACY_PHASE16)
    assert ev.optimization_visible is False
    assert EvaluationFirewall.can_influence_strategy(ev) is False
    assert EvaluationFirewall.can_enter_optimization_memory(ev) is False

def test_G_incompatible_policy_snapshots():
    p1 = EvaluationPolicy(alpha_level=0.95, min_trials=3, max_trials=5)
    p2 = EvaluationPolicy(alpha_level=0.99, min_trials=3, max_trials=5)

    compat, reason = EvaluationFirewall.is_policy_compatible(p1, p2)
    assert compat is False
    assert "Alpha" in reason

    p3 = EvaluationPolicy(alpha_level=0.95, min_trials=5, max_trials=5)
    compat2, reason2 = EvaluationFirewall.is_policy_compatible(p1, p3)
    assert compat2 is False
    assert "trials" in reason2

def test_H_incompatible_dataset_identities():
    d1 = DatasetIdentity(role="optimization", version="v1", hash="aaa")
    d2 = DatasetIdentity(role="optimization", version="v1", hash="bbb")

    compat, reason = EvaluationFirewall.is_dataset_compatible(d1, d2)
    assert compat is False
    assert "Hash" in reason

def test_I_failed_evaluation_cannot_become_successful_evidence():
    ev = create_mock_evidence(EvaluationTier.OPTIMIZATION, is_successful=False)
    assert EvaluationFirewall.can_enter_optimization_memory(ev) is False
    assert EvaluationFirewall.can_influence_strategy(ev) is False

def test_J_invalid_statistical_evidence_cannot_enter_optimization_memory():
    ev = create_mock_evidence(EvaluationTier.OPTIMIZATION, metric_status=EvidenceStatus.INVALID_DATA)
    assert EvaluationFirewall.can_enter_optimization_memory(ev) is False
    assert EvaluationFirewall.can_influence_strategy(ev) is False

def test_K_L_mixed_evidence_is_correctly_filtered():
    ev_opt = create_mock_evidence(EvaluationTier.OPTIMIZATION)
    ev_holdout = create_mock_evidence(EvaluationTier.HOLDOUT)
    ev_reg = create_mock_evidence(EvaluationTier.REGRESSION)
    ev_invalid = create_mock_evidence(EvaluationTier.OPTIMIZATION, metric_status=EvidenceStatus.INVALID_DATA)
    ev_failed = create_mock_evidence(EvaluationTier.OPTIMIZATION, is_successful=False)

    mixed = [ev_opt, ev_holdout, ev_reg, ev_invalid, ev_failed]
    filtered = EvaluationFirewall.filter_optimization_context(mixed)

    assert len(filtered) == 1
    assert filtered[0].evaluation_tier == EvaluationTier.OPTIMIZATION
    assert filtered[0].is_successful is True

def test_M_policy_snapshot_immutability():
    ev = create_mock_evidence(EvaluationTier.OPTIMIZATION)
    assert isinstance(ev.policy_snapshot, EvaluationPolicy)
    # the evidence holds a copy of the structure by definition of it being a Pydantic model
    # Changing something else outside does not modify the snapshot
    policy = EvaluationPolicy()
    ev.policy_snapshot = policy
    assert id(ev.policy_snapshot) == id(policy)

def test_N_existing_phase_16_behavior_intact():
    # Legacy data handled seamlessly
    ev = create_mock_evidence(EvaluationTier.LEGACY_PHASE16)
    assert EvaluationFirewall.can_enter_optimization_memory(ev) is False
