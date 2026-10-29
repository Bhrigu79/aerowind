from typing import List, Dict, Optional
from pydantic import BaseModel
from app.domain.types import DecisionResult, ConstraintEvaluation
from app.db.models import ExperimentRun, Experiment
from app.schemas.evaluation import EvaluationPolicy, ComparisonEvidence

class DecisionAssessment(BaseModel):
    result: DecisionResult
    rationale: str
    constraint_evaluations: List[ConstraintEvaluation] = []
    comparative_evidence: Dict[str, ComparisonEvidence] = {}
    holdout_evidence: Dict[str, ComparisonEvidence] = {}
    regression_evidence: Dict[str, ComparisonEvidence] = {}

class DecisionPolicyEvaluator:
    @staticmethod
    def evaluate(
        policy: EvaluationPolicy,
        execution_success: bool,
        evidence_corrupt: bool,
        constraint_evidence: List[ConstraintEvaluation],
        comparative_evidence: Dict[str, ComparisonEvidence] = None,
        holdout_evidence: Dict[str, ComparisonEvidence] = None,
        regression_evidence: Dict[str, ComparisonEvidence] = None
    ) -> DecisionAssessment:

        comparative_evidence = comparative_evidence or {}
        holdout_evidence = holdout_evidence or {}
        regression_evidence = regression_evidence or {}

        if evidence_corrupt:
            return DecisionAssessment(
                result=DecisionResult.REJECT,
                rationale="Evidence is explicitly corrupt or incompatible.",
                constraint_evaluations=constraint_evidence,
                comparative_evidence=comparative_evidence,
                holdout_evidence=holdout_evidence,
                regression_evidence=regression_evidence
            )

        if not execution_success:
            return DecisionAssessment(
                result=DecisionResult.INCONCLUSIVE,
                rationale="Execution failed (e.g. runner exception, timeout, unavailable).",
                constraint_evaluations=constraint_evidence,
                comparative_evidence=comparative_evidence,
                holdout_evidence=holdout_evidence,
                regression_evidence=regression_evidence
            )

        failed_constraints = [c for c in constraint_evidence if not c.passed and not c.missing_metric and c.evidence_valid]
        missing_constraints = [c for c in constraint_evidence if c.missing_metric]
        invalid_constraints = [c for c in constraint_evidence if not c.evidence_valid and not c.missing_metric]

        if failed_constraints:
            reasons = ", ".join([f"{e.metric_name} failed" for e in failed_constraints])
            return DecisionAssessment(
                result=DecisionResult.REJECT,
                rationale=f"Required hard constraints failed: {reasons}",
                constraint_evaluations=constraint_evidence,
                comparative_evidence=comparative_evidence,
                holdout_evidence=holdout_evidence,
                regression_evidence=regression_evidence
            )

        if missing_constraints or invalid_constraints:
            return DecisionAssessment(
                result=DecisionResult.INCONCLUSIVE,
                rationale="Required constraint evidence is missing or invalid.",
                constraint_evaluations=constraint_evidence,
                comparative_evidence=comparative_evidence,
                holdout_evidence=holdout_evidence,
                regression_evidence=regression_evidence
            )

        # 2. Check Generalization Evidence
        if policy.require_holdout_validation:
            if not holdout_evidence:
                return DecisionAssessment(
                    result=DecisionResult.INCONCLUSIVE,
                    rationale="Required holdout evidence is absent.",
                    constraint_evaluations=constraint_evidence,
                    comparative_evidence=comparative_evidence,
                    holdout_evidence=holdout_evidence,
                    regression_evidence=regression_evidence
                )
            for m_name, ev in holdout_evidence.items():
                if not ev.candidate_stats.valid:
                    return DecisionAssessment(
                        result=DecisionResult.INCONCLUSIVE,
                        rationale=f"Holdout evidence for {m_name} is invalid.",
                        constraint_evaluations=constraint_evidence,
                        comparative_evidence=comparative_evidence,
                        holdout_evidence=holdout_evidence,
                        regression_evidence=regression_evidence
                    )
                # A significant regression on ANY generalization metric is a REJECT.
                if ev.comparison.significant_regression:
                    return DecisionAssessment(
                        result=DecisionResult.REJECT,
                        rationale="Holdout validation failed (significant degradation).",
                        constraint_evaluations=constraint_evidence,
                        comparative_evidence=comparative_evidence,
                        holdout_evidence=holdout_evidence,
                        regression_evidence=regression_evidence
                    )

        if policy.require_regression_validation:
            if not regression_evidence:
                return DecisionAssessment(
                    result=DecisionResult.INCONCLUSIVE,
                    rationale="Required regression evidence is absent.",
                    constraint_evaluations=constraint_evidence,
                    comparative_evidence=comparative_evidence,
                    holdout_evidence=holdout_evidence,
                    regression_evidence=regression_evidence
                )
            for m_name, ev in regression_evidence.items():
                if not ev.candidate_stats.valid:
                    return DecisionAssessment(
                        result=DecisionResult.INCONCLUSIVE,
                        rationale=f"Regression evidence for {m_name} is invalid.",
                        constraint_evaluations=constraint_evidence,
                        comparative_evidence=comparative_evidence,
                        holdout_evidence=holdout_evidence,
                        regression_evidence=regression_evidence
                    )
                if ev.comparison.significant_regression:
                    return DecisionAssessment(
                        result=DecisionResult.REJECT,
                        rationale="Regression validation failed (significant degradation).",
                        constraint_evaluations=constraint_evidence,
                        comparative_evidence=comparative_evidence,
                        holdout_evidence=holdout_evidence,
                        regression_evidence=regression_evidence
                    )

        # 3. Check Comparative Evidence
        if policy.require_comparative_improvement:
            if not comparative_evidence:
                return DecisionAssessment(
                    result=DecisionResult.INCONCLUSIVE,
                    rationale="Required comparative evidence is missing.",
                    constraint_evaluations=constraint_evidence,
                    comparative_evidence=comparative_evidence,
                    holdout_evidence=holdout_evidence,
                    regression_evidence=regression_evidence
                )

            # Ensure ALL required comparative metrics demonstrate improvement
            if policy.required_comparative_metrics:
                for req_metric in policy.required_comparative_metrics:
                    if req_metric not in comparative_evidence:
                        return DecisionAssessment(
                            result=DecisionResult.INCONCLUSIVE,
                            rationale=f"Required comparative evidence for {req_metric} is missing.",
                            constraint_evaluations=constraint_evidence,
                            comparative_evidence=comparative_evidence,
                            holdout_evidence=holdout_evidence,
                            regression_evidence=regression_evidence
                        )

                    ev = comparative_evidence[req_metric]
                    if ev.candidate_stats.is_legacy or ev.baseline_stats.is_legacy:
                        return DecisionAssessment(
                            result=DecisionResult.INCONCLUSIVE,
                            rationale=f"Legacy evidence for {req_metric} cannot satisfy comparative improvement requirements.",
                            constraint_evaluations=constraint_evidence,
                            comparative_evidence=comparative_evidence,
                            holdout_evidence=holdout_evidence,
                            regression_evidence=regression_evidence
                        )

                    if ev.comparison.significant_regression:
                        return DecisionAssessment(
                            result=DecisionResult.REJECT,
                            rationale=f"Required comparative metric {req_metric} significantly regressed.",
                            constraint_evaluations=constraint_evidence,
                            comparative_evidence=comparative_evidence,
                            holdout_evidence=holdout_evidence,
                            regression_evidence=regression_evidence
                        )

                    if not (ev.comparison.statistically_supported and ev.comparison.effect_above_mpe):
                        return DecisionAssessment(
                            result=DecisionResult.INCONCLUSIVE,
                            rationale=f"Required comparative improvement for {req_metric} not supported by statistical evidence.",
                            constraint_evaluations=constraint_evidence,
                            comparative_evidence=comparative_evidence,
                            holdout_evidence=holdout_evidence,
                            regression_evidence=regression_evidence
                        )
            else:
                # If no specific metrics requested, at least one must improve, and NONE can significantly regress
                improved = False
                for m_name, ev in comparative_evidence.items():
                    if ev.candidate_stats.is_legacy or ev.baseline_stats.is_legacy:
                        return DecisionAssessment(
                            result=DecisionResult.INCONCLUSIVE,
                            rationale="Legacy evidence cannot satisfy comparative improvement requirements.",
                            constraint_evaluations=constraint_evidence,
                            comparative_evidence=comparative_evidence,
                            holdout_evidence=holdout_evidence,
                            regression_evidence=regression_evidence
                        )
                    if ev.comparison.significant_regression:
                        return DecisionAssessment(
                            result=DecisionResult.REJECT,
                            rationale=f"Comparative metric {m_name} significantly regressed.",
                            constraint_evaluations=constraint_evidence,
                            comparative_evidence=comparative_evidence,
                            holdout_evidence=holdout_evidence,
                            regression_evidence=regression_evidence
                        )
                    if ev.comparison.statistically_supported and ev.comparison.effect_above_mpe:
                        improved = True

                if not improved:
                    return DecisionAssessment(
                        result=DecisionResult.INCONCLUSIVE,
                        rationale="Required comparative improvement not supported by statistical evidence.",
                        constraint_evaluations=constraint_evidence,
                        comparative_evidence=comparative_evidence,
                        holdout_evidence=holdout_evidence,
                        regression_evidence=regression_evidence
                    )

        return DecisionAssessment(
            result=DecisionResult.RETAIN,
            rationale="All constraints and policy requirements satisfied.",
            constraint_evaluations=constraint_evidence,
            comparative_evidence=comparative_evidence,
            holdout_evidence=holdout_evidence,
            regression_evidence=regression_evidence
        )

class DecisionEngine:
    @staticmethod
    def decide(experiment: Experiment, run: ExperimentRun, evaluations: List[ConstraintEvaluation]) -> tuple[DecisionResult, str]:
        # Legacy adapter method for existing orchestrator calls
        if not run.success:
            return DecisionResult.INCONCLUSIVE, f"Execution failed: {run.error_info}"

        if any(e.missing_metric for e in evaluations):
            return DecisionResult.INCONCLUSIVE, "One or more required metrics were missing from the run results."

        failed_constraints = [e for e in evaluations if not e.passed]

        if failed_constraints:
            reasons = ", ".join([f"{e.metric_name} ({e.actual_value} not {e.operator.value} {e.required_value})" for e in failed_constraints])
            return DecisionResult.REJECT, f"Failed constraints: {reasons}"

        return DecisionResult.RETAIN, "All constraints satisfied."
