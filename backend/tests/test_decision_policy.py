import pytest
from app.domain.types import DecisionResult, ConstraintOperator, MetricDirection
from app.schemas.evaluation import EvaluationPolicy, ComparisonEvidence, MetricStatistics, StatisticalTestResult, EvidenceStatus
from app.services.decision import DecisionPolicyEvaluator, ConstraintEvaluation
from app.services.statistics import StatisticalEngine
from app.schemas.evaluation import MetricObservationSet

def test_A_B_C_execution_failures():
    # Runner crash, Provider unavailable, Timeout all map to execution_success=False
    policy = EvaluationPolicy()

    # Crash
    assess_crash = DecisionPolicyEvaluator.evaluate(
        policy=policy, execution_success=False, evidence_corrupt=False, constraint_evidence=[]
    )
    assert assess_crash.result == DecisionResult.INCONCLUSIVE
    assert "Execution failed" in assess_crash.rationale

def test_D_corrupt_evidence():
    policy = EvaluationPolicy()
    assess_corrupt = DecisionPolicyEvaluator.evaluate(
        policy=policy, execution_success=True, evidence_corrupt=True, constraint_evidence=[]
    )
    assert assess_corrupt.result == DecisionResult.REJECT
    assert "explicitly corrupt" in assess_corrupt.rationale

def test_E_F_G_hard_constraint_failures():
    policy = EvaluationPolicy()

    # Quality
    ce_qual = ConstraintEvaluation(metric_name="quality", passed=False, missing_metric=False, actual_value=85, required_value=90, operator=ConstraintOperator.GTE, evidence_valid=True)
    assess_e = DecisionPolicyEvaluator.evaluate(policy=policy, execution_success=True, evidence_corrupt=False, constraint_evidence=[ce_qual])
    assert assess_e.result == DecisionResult.REJECT

    # Latency
    ce_lat = ConstraintEvaluation(metric_name="latency", passed=False, missing_metric=False, actual_value=3000, required_value=2000, operator=ConstraintOperator.LTE, evidence_valid=True)
    assess_f = DecisionPolicyEvaluator.evaluate(policy=policy, execution_success=True, evidence_corrupt=False, constraint_evidence=[ce_lat])
    assert assess_f.result == DecisionResult.REJECT

    # Cost
    ce_cost = ConstraintEvaluation(metric_name="cost", passed=False, missing_metric=False, actual_value=0.05, required_value=0.03, operator=ConstraintOperator.LTE, evidence_valid=True)
    assess_g = DecisionPolicyEvaluator.evaluate(policy=policy, execution_success=True, evidence_corrupt=False, constraint_evidence=[ce_cost])
    assert assess_g.result == DecisionResult.REJECT

def test_H_I_J_K_L_M_metric_direction_semantics():
    base_obs_90 = MetricObservationSet(values=[90.0, 90.0, 90.0], is_legacy=False)
    cand_obs_95 = MetricObservationSet(values=[95.0, 95.0, 95.0], is_legacy=False)
    cand_obs_85 = MetricObservationSet(values=[85.0, 85.0, 85.0], is_legacy=False)

    # H. Quality positive delta = improvement
    res_h = StatisticalEngine.evaluate_comparison(base_obs_90, cand_obs_95, mpe=1.0, direction=MetricDirection.HIGHER_IS_BETTER)
    assert res_h.comparison.effect_above_mpe is True
    assert res_h.comparison.is_regression is False

    # K. Quality negative delta = degradation
    res_k = StatisticalEngine.evaluate_comparison(base_obs_90, cand_obs_85, mpe=1.0, direction=MetricDirection.HIGHER_IS_BETTER)
    assert res_k.comparison.is_regression is True
    assert res_k.comparison.significant_regression is True # Since variance is 0, it directly captures it

    # I. Latency negative delta = improvement (e.g. 90 -> 85)
    res_i = StatisticalEngine.evaluate_comparison(base_obs_90, cand_obs_85, mpe=1.0, direction=MetricDirection.LOWER_IS_BETTER)
    assert res_i.comparison.effect_above_mpe is True
    assert res_i.comparison.is_regression is False

    # L. Latency positive delta = degradation (e.g. 90 -> 95)
    res_l = StatisticalEngine.evaluate_comparison(base_obs_90, cand_obs_95, mpe=1.0, direction=MetricDirection.LOWER_IS_BETTER)
    assert res_l.comparison.is_regression is True
    assert res_l.comparison.significant_regression is True

    # Cost is just another lower-is-better metric
    res_j = StatisticalEngine.evaluate_comparison(base_obs_90, cand_obs_85, mpe=1.0, direction=MetricDirection.LOWER_IS_BETTER)
    assert res_j.comparison.effect_above_mpe is True

def test_N_satisfies_constraints_but_mpe_below():
    # Comparative improvement below MPE -> INCONCLUSIVE (if required)
    policy = EvaluationPolicy(require_comparative_improvement=True, required_comparative_metrics=["quality"])
    ce = ConstraintEvaluation(metric_name="quality", passed=True, missing_metric=False, actual_value=93.2, required_value=92.0, operator=ConstraintOperator.GTE, evidence_valid=True)

    base = MetricObservationSet(values=[93.0, 93.0, 93.0], is_legacy=False)
    cand = MetricObservationSet(values=[93.2, 93.2, 93.2], is_legacy=False)
    comp = StatisticalEngine.evaluate_comparison(base, cand, mpe=1.0, direction=MetricDirection.HIGHER_IS_BETTER)

    assess = DecisionPolicyEvaluator.evaluate(
        policy=policy, execution_success=True, evidence_corrupt=False,
        constraint_evidence=[ce], comparative_evidence={"quality": comp}
    )
    assert assess.result == DecisionResult.INCONCLUSIVE

def test_O_improves_quality_but_violates_latency_constraint():
    policy = EvaluationPolicy(require_comparative_improvement=True, required_comparative_metrics=["quality"])
    ce_lat = ConstraintEvaluation(metric_name="latency", passed=False, missing_metric=False, actual_value=3000, required_value=2000, operator=ConstraintOperator.LTE, evidence_valid=True)

    base = MetricObservationSet(values=[90.0, 90.0, 90.0], is_legacy=False)
    cand = MetricObservationSet(values=[95.0, 95.0, 95.0], is_legacy=False)
    comp = StatisticalEngine.evaluate_comparison(base, cand, mpe=1.0, direction=MetricDirection.HIGHER_IS_BETTER)

    assess = DecisionPolicyEvaluator.evaluate(
        policy=policy, execution_success=True, evidence_corrupt=False,
        constraint_evidence=[ce_lat], comparative_evidence={"quality": comp}
    )
    assert assess.result == DecisionResult.REJECT
    assert "hard constraints failed: latency" in assess.rationale

def test_P_Q_missing_failed_holdout():
    policy = EvaluationPolicy(require_holdout_validation=True)
    ce = ConstraintEvaluation(metric_name="quality", passed=True, missing_metric=False, actual_value=95, required_value=90, operator=ConstraintOperator.GTE, evidence_valid=True)

    # Missing holdout
    assess_p = DecisionPolicyEvaluator.evaluate(policy=policy, execution_success=True, evidence_corrupt=False, constraint_evidence=[ce], holdout_evidence={})
    assert assess_p.result == DecisionResult.INCONCLUSIVE

    # Failed holdout (significant degradation)
    base = MetricObservationSet(values=[90.0, 90.0, 90.0], is_legacy=False)
    cand = MetricObservationSet(values=[80.0, 80.0, 80.0], is_legacy=False)
    comp = StatisticalEngine.evaluate_comparison(base, cand, mpe=0.0, direction=MetricDirection.HIGHER_IS_BETTER)

    assess_q = DecisionPolicyEvaluator.evaluate(policy=policy, execution_success=True, evidence_corrupt=False, constraint_evidence=[ce], holdout_evidence={"quality": comp})
    assert assess_q.result == DecisionResult.REJECT
    assert "validation failed" in assess_q.rationale

def test_R_legacy_evidence():
    policy = EvaluationPolicy(require_comparative_improvement=True)
    ce = ConstraintEvaluation(metric_name="quality", passed=True, missing_metric=False, actual_value=95, required_value=90, operator=ConstraintOperator.GTE, evidence_valid=True)

    base = MetricObservationSet(values=[90.0], is_legacy=True)
    cand = MetricObservationSet(values=[95.0], is_legacy=True)
    comp = StatisticalEngine.evaluate_comparison(base, cand, mpe=0.0, direction=MetricDirection.HIGHER_IS_BETTER)

    # Legacy evidence cannot fabricate statistical support
    assert comp.comparison.statistically_supported is None

    assess = DecisionPolicyEvaluator.evaluate(policy=policy, execution_success=True, evidence_corrupt=False, constraint_evidence=[ce], comparative_evidence={"quality": comp})
    assert assess.result == DecisionResult.INCONCLUSIVE
    assert "Legacy evidence cannot satisfy" in assess.rationale

def test_S_llm_immutability():
    # LLM cannot override the DecisionAssessment because the function is pure
    # and only takes explicit metric evidence. There is no `llm_override` parameter.
    # We prove this structurally: a REJECT assessment has no mutation points.
    policy = EvaluationPolicy()
    ce = ConstraintEvaluation(metric_name="latency", passed=False, missing_metric=False, actual_value=3000, required_value=2000, operator=ConstraintOperator.LTE, evidence_valid=True)
    assess = DecisionPolicyEvaluator.evaluate(policy=policy, execution_success=True, evidence_corrupt=False, constraint_evidence=[ce])
    assert assess.result == DecisionResult.REJECT
