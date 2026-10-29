from typing import List, Tuple, Optional
from app.schemas.evaluation import EvaluationEvidence, EvaluationTier, EvaluationPolicy, DatasetIdentity, EvidenceStatus

class EvaluationFirewall:
    @staticmethod
    def _is_valid_evidence(evidence: EvaluationEvidence) -> bool:
        if not evidence.is_successful:
            return False

        for metric_name, comp_ev in evidence.metrics.items():
            if comp_ev.comparison.status == EvidenceStatus.INVALID_DATA:
                return False

        return True

    @staticmethod
    def can_enter_optimization_memory(evidence: EvaluationEvidence) -> bool:
        if not EvaluationFirewall._is_valid_evidence(evidence):
            return False
        return evidence.optimization_visible

    @staticmethod
    def can_influence_strategy(evidence: EvaluationEvidence) -> bool:
        if not EvaluationFirewall._is_valid_evidence(evidence):
            return False
        return evidence.evaluation_tier == EvaluationTier.OPTIMIZATION

    @staticmethod
    def can_influence_hypothesis_generation(evidence: EvaluationEvidence) -> bool:
        if not EvaluationFirewall._is_valid_evidence(evidence):
            return False
        return evidence.evaluation_tier == EvaluationTier.OPTIMIZATION

    @staticmethod
    def can_be_used_for_final_validation(evidence: EvaluationEvidence) -> bool:
        if not EvaluationFirewall._is_valid_evidence(evidence):
            return False
        return evidence.evaluation_tier in [EvaluationTier.REGRESSION, EvaluationTier.HOLDOUT]

    @staticmethod
    def filter_optimization_context(evidences: List[EvaluationEvidence]) -> List[EvaluationEvidence]:
        """
        Ensures regression/holdout/legacy/invalid data does not leak into optimization context.
        """
        return [
            ev for ev in evidences
            if EvaluationFirewall.can_enter_optimization_memory(ev)
        ]

    @staticmethod
    def is_policy_compatible(policy1: EvaluationPolicy, policy2: EvaluationPolicy) -> Tuple[bool, Optional[str]]:
        if policy1.alpha_level != policy2.alpha_level:
            return False, "Alpha levels differ"

        if policy1.require_comparative_improvement != policy2.require_comparative_improvement:
            return False, "Comparative improvement requirement differs"

        if policy1.failure_tolerance_ratio != policy2.failure_tolerance_ratio:
            return False, "Failure tolerance ratio differs"

        if policy1.min_trials != policy2.min_trials:
            return False, "Minimum trials differ"

        if policy1.max_trials != policy2.max_trials:
            return False, "Maximum trials differ"

        if policy1.mpe_thresholds != policy2.mpe_thresholds:
            return False, "MPE thresholds differ"

        return True, None

    @staticmethod
    def is_dataset_compatible(dataset1: DatasetIdentity, dataset2: DatasetIdentity) -> Tuple[bool, Optional[str]]:
        if dataset1.role != dataset2.role:
            return False, f"Roles differ: {dataset1.role} vs {dataset2.role}"
        if dataset1.hash != dataset2.hash:
            return False, f"Hashes differ: {dataset1.hash} vs {dataset2.hash}"
        # A hash match implies the exact data is identical.
        # But we also enforce version match to prevent silent semantic shifts.
        if dataset1.version != dataset2.version:
            return False, f"Versions differ: {dataset1.version} vs {dataset2.version}"

        return True, None
