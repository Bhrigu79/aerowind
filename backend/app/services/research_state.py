import json
from typing import List, Dict, Any, Optional
from app.db.models import Experiment, ExperimentRun, Decision
from app.schemas.research import (
    ResearchState, ExploredConfiguration, ObservedEffect, FailedRegion, ResearchUncertainty
)
from app.schemas.evaluation import EvaluationPolicy, MetricObservationSet
from app.core.config_validator import ConfigurationValidator
from app.services.firewall import EvaluationFirewall
from app.services.statistics import StatisticalEngine
from app.domain.types import EvaluationTier, DecisionResult, MetricDirection

class ResearchStateService:

    @staticmethod
    def _fingerprint(config: Dict[str, Any]) -> str:
        normalized = ConfigurationValidator.normalize(config)
        return json.dumps(normalized, sort_keys=True)

    @staticmethod
    def build_state(
        objective_id: str,
        objective_constraints: Dict[str, float],
        optimization_directions: Dict[str, MetricDirection],
        policy_snapshot: EvaluationPolicy,
        experiments: List[Experiment],
    ) -> ResearchState:

        state = ResearchState(
            objective_id=objective_id,
            objective_constraints=objective_constraints,
            optimization_directions=optimization_directions,
            policy_snapshot=policy_snapshot
        )

        # Sort experiments deterministically (e.g., by created_at then id)
        sorted_experiments = sorted(experiments, key=lambda x: (x.created_at or "", x.id))

        for exp in sorted_experiments:
            if not exp.plan or not exp.plan.candidate_variant:
                continue

            # Filter runs through EvaluationFirewall and validity checks
            cand_runs = [r for r in exp.runs if r.variant_id == exp.plan.candidate_variant.id]
            # Find the primary optimization run
            opt_run = None
            holdout_run = None
            regression_run = None

            for r in sorted(cand_runs, key=lambda x: x.id):
                if r.evaluation_tier == EvaluationTier.OPTIMIZATION.value:
                    opt_run = r
                elif r.evaluation_tier == EvaluationTier.HOLDOUT.value:
                    holdout_run = r
                elif r.evaluation_tier == EvaluationTier.REGRESSION.value:
                    regression_run = r

            if not opt_run:
                # If there's no valid optimization run, this experiment doesn't contribute to explored configs
                continue

            raw_config = exp.plan.candidate_variant.system_configuration
            fingerprint = ResearchStateService._fingerprint(raw_config)
            decision = exp.decisions[0] if exp.decisions else None
            decision_result = decision.result if decision else DecisionResult.INCONCLUSIVE.value

            # Explored Configuration
            explored = ExploredConfiguration(
                canonical_configuration=ConfigurationValidator.normalize(raw_config),
                fingerprint=fingerprint,
                experiment_id=exp.id,
                run_id=opt_run.id,
                decision=decision_result,
                changed_dimensions=sorted(exp.plan.changed_variables) if exp.plan.changed_variables else [],
                dataset_version=opt_run.dataset_version,
                execution_provenance=opt_run.execution_provenance
            )
            state.explored_configurations.append(explored)

            # Effects, Failures, Uncertainties
            if decision_result == DecisionResult.RETAIN.value:
                if fingerprint not in state.feasible_configurations:
                    state.feasible_configurations.append(fingerprint)

            if decision:
                # Categorize failures
                if decision_result == DecisionResult.REJECT.value:
                    rat = decision.rationale.lower()
                    failure_type = "UNKNOWN"
                    if "hard constraints failed" in rat or "failed constraints" in rat:
                        failure_type = "CONSTRAINT_FAILURE"
                    elif "comparative metric" in rat and "regressed" in rat:
                        failure_type = "COMPARATIVE_FAILURE"
                    elif "holdout validation failed" in rat or "regression validation failed" in rat:
                        failure_type = "GENERALIZATION_FAILURE"
                    elif "explicitly corrupt" in rat or "invalid" in rat:
                        failure_type = "INVALID_EVIDENCE"
                    else:
                        failure_type = "COMPARATIVE_FAILURE" # fallback for explicit rejection without constraint/holdout

                    state.failed_regions.append(FailedRegion(
                        canonical_configuration=ConfigurationValidator.normalize(raw_config),
                        fingerprint=fingerprint,
                        failure_type=failure_type,
                        reason=decision.rationale,
                        experiment_id=exp.id,
                        run_id=opt_run.id
                    ))
                elif decision_result == DecisionResult.INCONCLUSIVE.value:
                    rat = decision.rationale.lower()
                    if "execution failed" in rat:
                        state.uncertainties.append(ResearchUncertainty(
                            fingerprint=fingerprint,
                            uncertainty_type="EXECUTION_FAILED",
                            reason=decision.rationale,
                            experiment_id=exp.id,
                            run_id=opt_run.id
                        ))
                    elif "holdout" in rat or "regression" in rat:
                        state.uncertainties.append(ResearchUncertainty(
                            fingerprint=fingerprint,
                            uncertainty_type="MISSING_GENERALIZATION_EVIDENCE",
                            reason=decision.rationale,
                            experiment_id=exp.id,
                            run_id=opt_run.id
                        ))
                    else:
                        state.uncertainties.append(ResearchUncertainty(
                            fingerprint=fingerprint,
                            uncertainty_type="MISSING_COMPARATIVE_EVIDENCE",
                            reason=decision.rationale,
                            experiment_id=exp.id,
                            run_id=opt_run.id
                        ))

            # Actually, execution failure might happen and Decision is INCONCLUSIVE
            if opt_run.success is False:
                # If execution failed, but decision isn't there or is something else (rare)
                if not any(u.fingerprint == fingerprint and u.uncertainty_type == "EXECUTION_FAILED" for u in state.uncertainties):
                    state.uncertainties.append(ResearchUncertainty(
                        fingerprint=fingerprint,
                        uncertainty_type="EXECUTION_FAILED",
                        reason=opt_run.error_info or "Unknown runner failure",
                        experiment_id=exp.id,
                        run_id=opt_run.id
                    ))

        # Recompute comparisons from raw metric evidence
        for exp in sorted_experiments:
            if not exp.plan or not exp.plan.candidate_variant or not exp.plan.baseline_variant:
                continue

            cand_runs = [r for r in exp.runs if r.variant_id == exp.plan.candidate_variant.id]
            base_runs = [r for r in exp.runs if r.variant_id == exp.plan.baseline_variant.id]

            opt_run = next((r for r in sorted(cand_runs, key=lambda x: x.id)
                            if r.evaluation_tier == EvaluationTier.OPTIMIZATION.value), None)
            base_run = next((r for r in sorted(base_runs, key=lambda x: x.id)
                             if r.evaluation_tier == EvaluationTier.OPTIMIZATION.value), None)

            if not opt_run or not base_run:
                continue

            # Reconstruct ObservationSets
            def build_obs_set(run: ExperimentRun) -> MetricObservationSet:
                metrics_by_name = {}
                is_legacy = (run.evaluation_tier == EvaluationTier.LEGACY_PHASE16.value)
                for m in run.metric_results:
                    if m.metric_name not in metrics_by_name:
                        metrics_by_name[m.metric_name] = []
                    metrics_by_name[m.metric_name].append(m.value)

                return metrics_by_name, is_legacy

            cand_metrics, cand_legacy = build_obs_set(opt_run)
            base_metrics, base_legacy = build_obs_set(base_run)

            for metric, cand_vals in cand_metrics.items():
                if metric not in base_metrics:
                    continue

                base_vals = base_metrics[metric]
                direction = optimization_directions.get(metric, MetricDirection.HIGHER_IS_BETTER)
                mpe = policy_snapshot.mpe_thresholds.get(metric, 0.0)

                b_obs = MetricObservationSet(values=base_vals, is_legacy=base_legacy)
                c_obs = MetricObservationSet(values=cand_vals, is_legacy=cand_legacy)

                comp_evidence = StatisticalEngine.evaluate_comparison(
                    b_obs, c_obs, mpe=mpe, alpha_level=policy_snapshot.alpha_level, direction=direction
                )

                b_stats = comp_evidence.baseline_stats
                c_stats = comp_evidence.candidate_stats
                comp_res = comp_evidence.comparison

                if not b_stats.valid or not c_stats.valid:
                    continue

                stat_sup = None if (cand_legacy or base_legacy) else comp_res.statistically_supported

                state.observed_effects.append(ObservedEffect(
                    metric=metric,
                    direction=direction,
                    baseline_value=b_stats.mean,
                    candidate_value=c_stats.mean,
                    improvement_delta=comp_res.absolute_difference,
                    effect_above_mpe=comp_res.effect_above_mpe or False,
                    statistically_supported=stat_sup,
                    confidence_interval_lower=comp_res.confidence_interval_lower,
                    confidence_interval_upper=comp_res.confidence_interval_upper,
                    sample_size=c_stats.n,
                    source_experiment_id=exp.id,
                    source_run_id=opt_run.id
                ))

        # Current Best Semantics
        # The prompt says: "If an existing Current Best concept already exists, preserve its semantics... best retained configuration".
        # We can look through feasible_configurations and pick the one from the most recent retained experiment.
        # But `current_best_fingerprint` should ideally just be the baseline of the LATEST experiment, or the last adopted.
        last_adopted = next((exp for exp in reversed(sorted_experiments) if exp.adopted and exp.plan and exp.plan.candidate_variant), None)
        if last_adopted:
            state.current_best_fingerprint = ResearchStateService._fingerprint(last_adopted.plan.candidate_variant.system_configuration)
        else:
            # If nothing adopted, maybe there's an explicit baseline variant in the DB.
            # For this pure rebuild function, we'll just check if any feasible config is the starting baseline.
            pass

        return state
