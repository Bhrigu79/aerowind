import uuid
import hashlib
from typing import List, Optional
from app.schemas.research import (
    ResearchState, ParetoFrontier, ResearchCritique, CritiqueType, CritiqueStatus
)
from app.db.models import Experiment
from app.domain.types import DecisionResult, EvaluationTier

class SelfAdversarialCritiqueEngine:
    @staticmethod
    def _generate_critique_id(target_id: str, critique_type: str) -> str:
        m = hashlib.md5()
        m.update(target_id.encode('utf-8'))
        m.update(critique_type.encode('utf-8'))
        return str(uuid.UUID(m.hexdigest()))

    @staticmethod
    def evaluate(
        research_state: ResearchState,
        pareto_frontier: Optional[ParetoFrontier] = None,
        experiments: Optional[List[Experiment]] = None,
        search_exhausted: bool = False
    ) -> List[ResearchCritique]:
        critiques = []
        experiments = experiments or []

        for config in sorted(research_state.explored_configurations, key=lambda x: x.fingerprint):
            run_effects = [e for e in research_state.observed_effects if e.source_run_id == config.run_id]
            run_effects = sorted(run_effects, key=lambda e: e.metric)

            # A, C, D apply mainly when a config is retained (we trust it)
            if config.decision == DecisionResult.RETAIN.value:
                for effect in run_effects:
                    # A. Insufficient trials
                    if effect.sample_size < research_state.policy_snapshot.min_trials:
                        critiques.append(ResearchCritique(
                            critique_id=SelfAdversarialCritiqueEngine._generate_critique_id(config.fingerprint, f"{CritiqueType.INSUFFICIENT_TRIALS}_{effect.metric}"),
                            target_type="METRIC_RESULT",
                            target_id=effect.metric,
                            critique_type=CritiqueType.INSUFFICIENT_TRIALS,
                            severity="HIGH",
                            claim=f"Metric {effect.metric} only has {effect.sample_size} trials, but policy requires {research_state.policy_snapshot.min_trials}.",
                            evidence_refs=[effect.source_run_id],
                            status=CritiqueStatus.VERIFIED,
                            deterministic_reason="Observed effect sample_size < policy.min_trials"
                        ))

                    # C. Weak effect
                    if not effect.effect_above_mpe and effect.candidate_value is not None and effect.baseline_value is not None:
                        critiques.append(ResearchCritique(
                            critique_id=SelfAdversarialCritiqueEngine._generate_critique_id(config.fingerprint, f"{CritiqueType.WEAK_EFFECT}_{effect.metric}"),
                            target_type="METRIC_RESULT",
                            target_id=effect.metric,
                            critique_type=CritiqueType.WEAK_EFFECT,
                            severity="LOW",
                            claim=f"Observed effect for {effect.metric} does not exceed MPE threshold.",
                            evidence_refs=[effect.source_run_id],
                            status=CritiqueStatus.VERIFIED,
                            deterministic_reason="effect_above_mpe == False"
                        ))

                    # D. Statistical uncertainty
                    if effect.statistically_supported is False:
                        critiques.append(ResearchCritique(
                            critique_id=SelfAdversarialCritiqueEngine._generate_critique_id(config.fingerprint, f"{CritiqueType.SIGNIFICANCE_NOT_ESTABLISHED}_{effect.metric}"),
                            target_type="METRIC_RESULT",
                            target_id=effect.metric,
                            critique_type=CritiqueType.SIGNIFICANCE_NOT_ESTABLISHED,
                            severity="MEDIUM",
                            claim=f"Observed effect for {effect.metric} lacks statistical support.",
                            evidence_refs=[effect.source_run_id],
                            status=CritiqueStatus.VERIFIED,
                            deterministic_reason="statistically_supported == False"
                        ))

                # F, G. Generalization & Regression Missing
                exp = next((e for e in experiments if e.id == config.experiment_id), None)
                if exp:
                    if research_state.policy_snapshot.require_holdout_validation:
                        has_holdout = any(r.evaluation_tier == EvaluationTier.HOLDOUT.value and r.success for r in exp.runs)
                        if not has_holdout:
                            critiques.append(ResearchCritique(
                                critique_id=SelfAdversarialCritiqueEngine._generate_critique_id(config.fingerprint, CritiqueType.GENERALIZATION_UNVERIFIED),
                                target_type="CONFIGURATION",
                                target_id=config.fingerprint,
                                critique_type=CritiqueType.GENERALIZATION_UNVERIFIED,
                                severity="HIGH",
                                claim="Holdout validation is required by policy but is missing.",
                                evidence_refs=[config.experiment_id],
                                status=CritiqueStatus.VERIFIED,
                                deterministic_reason="No successful HOLDOUT run found"
                            ))

                    if research_state.policy_snapshot.require_regression_validation:
                        has_regression = any(r.evaluation_tier == EvaluationTier.REGRESSION.value and r.success for r in exp.runs)
                        if not has_regression:
                            critiques.append(ResearchCritique(
                                critique_id=SelfAdversarialCritiqueEngine._generate_critique_id(config.fingerprint, CritiqueType.REGRESSION_UNVERIFIED),
                                target_type="CONFIGURATION",
                                target_id=config.fingerprint,
                                critique_type=CritiqueType.REGRESSION_UNVERIFIED,
                                severity="HIGH",
                                claim="Regression validation is required by policy but is missing.",
                                evidence_refs=[config.experiment_id],
                                status=CritiqueStatus.VERIFIED,
                                deterministic_reason="No successful REGRESSION run found"
                            ))

            # I. Dominated current best
            if pareto_frontier and pareto_frontier.current_best_fingerprint == config.fingerprint:
                if pareto_frontier.current_best_is_dominated:
                    critiques.append(ResearchCritique(
                        critique_id=SelfAdversarialCritiqueEngine._generate_critique_id(config.fingerprint, CritiqueType.DOMINATED_CURRENT_BEST),
                        target_type="CONFIGURATION",
                        target_id=config.fingerprint,
                        critique_type=CritiqueType.DOMINATED_CURRENT_BEST,
                        severity="MEDIUM",
                        claim="The current best configuration is explicitly dominated by the Pareto frontier.",
                        evidence_refs=[pareto_frontier.frontier_fingerprints[0] if pareto_frontier.frontier_fingerprints else config.fingerprint],
                        status=CritiqueStatus.VERIFIED,
                        deterministic_reason="current_best_is_dominated == True"
                    ))

            # J. Legacy Evidence (Missing trial provenance)
            exp = next((e for e in experiments if e.id == config.experiment_id), None)
            if exp:
                run = next((r for r in exp.runs if r.id == config.run_id), None)
                if run and run.metric_results:
                    legacy_metrics = [m for m in run.metric_results if not m.trial_id]
                    if legacy_metrics and research_state.policy_snapshot.min_trials > 1:
                        critiques.append(ResearchCritique(
                            critique_id=SelfAdversarialCritiqueEngine._generate_critique_id(config.fingerprint, CritiqueType.LEGACY_EVIDENCE),
                            target_type="EXPERIMENT_RUN",
                            target_id=run.id,
                            critique_type=CritiqueType.LEGACY_EVIDENCE,
                            severity="MEDIUM",
                            claim="Evidence lacks trial provenance while policy requires multiple trials.",
                            evidence_refs=[m.id for m in legacy_metrics],
                            status=CritiqueStatus.VERIFIED,
                            deterministic_reason="Legacy metrics found without trial_id"
                        ))

            # K. Missing Provenance
            if not config.execution_provenance:
                critiques.append(ResearchCritique(
                    critique_id=SelfAdversarialCritiqueEngine._generate_critique_id(config.fingerprint, CritiqueType.MISSING_PROVENANCE),
                    target_type="CONFIGURATION",
                    target_id=config.fingerprint,
                    critique_type=CritiqueType.MISSING_PROVENANCE,
                    severity="LOW",
                    claim="Configuration lacks explicit execution provenance.",
                    evidence_refs=[config.run_id],
                    status=CritiqueStatus.VERIFIED,
                    deterministic_reason="execution_provenance is empty or None"
                ))

        if search_exhausted:
            critiques.append(ResearchCritique(
                critique_id=SelfAdversarialCritiqueEngine._generate_critique_id(research_state.objective_id, CritiqueType.SEARCH_COVERAGE_LIMITED),
                target_type="RESEARCH_STATE",
                target_id=research_state.objective_id,
                critique_type=CritiqueType.SEARCH_COVERAGE_LIMITED,
                severity="MEDIUM",
                claim="Search space was exhausted or budget bounded.",
                evidence_refs=[research_state.objective_id],
                status=CritiqueStatus.VERIFIED,
                deterministic_reason="search_exhausted flag is True"
            ))

        # Deterministic deduplication in case duplicate effects existed (though they shouldn't if deduped properly)
        unique_critiques = {c.critique_id: c for c in critiques}

        return sorted(unique_critiques.values(), key=lambda c: c.critique_id)
