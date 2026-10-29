import math
from typing import List, Dict, Optional, Any
from app.schemas.research import (
    ResearchState,
    FailureAtlas,
    FailureAtlasEntry,
    FailedRegion
)
from app.schemas.evaluation import EvaluationPolicy
from app.domain.types import MetricDirection

class FailureAtlasService:
    @staticmethod
    def build_atlas(research_state: ResearchState) -> FailureAtlas:
        entries: Dict[str, FailureAtlasEntry] = {}

        # We process failed regions sequentially.
        # If multiple experiments hit the same canonical failed config,
        # we deterministic-tie-break (e.g. by lexicographical run_id)
        # to decide which evidence represents it, or we merge if appropriate.
        # Requirements: "one canonical configuration entry containing deterministic evidence references"
        # We will use the canonical fingerprint as the unique key.

        for failed_region in sorted(research_state.failed_regions, key=lambda x: x.run_id):
            fp = failed_region.fingerprint

            # Find all observed effects for this run
            run_effects = [e for e in research_state.observed_effects if e.source_run_id == failed_region.run_id]

            # Extract metric values
            observed_values = {}
            for e in run_effects:
                if e.candidate_value is not None and math.isfinite(e.candidate_value):
                    observed_values[e.metric] = e.candidate_value

            # Reconstruct failed constraints/metrics based on the failure type and evidence
            failed_constraints = []
            failed_metrics = []

            if failed_region.failure_type == "CONSTRAINT_FAILURE":
                # Find which constraints were violated
                for metric, required_val in research_state.objective_constraints.items():
                    if metric in observed_values:
                        val = observed_values[metric]
                        direction = research_state.optimization_directions.get(metric, MetricDirection.HIGHER_IS_BETTER)
                        if direction == MetricDirection.HIGHER_IS_BETTER and val < required_val:
                            failed_constraints.append(metric)
                        elif direction == MetricDirection.LOWER_IS_BETTER and val > required_val:
                            failed_constraints.append(metric)

            elif failed_region.failure_type == "COMPARATIVE_FAILURE":
                for e in run_effects:
                    direction = research_state.optimization_directions.get(e.metric, MetricDirection.HIGHER_IS_BETTER)
                    if e.baseline_value is not None and e.candidate_value is not None:
                        # significant regression logic (simple approximation since we don't have the raw t-test here)
                        if direction == MetricDirection.HIGHER_IS_BETTER and e.candidate_value < e.baseline_value and e.statistically_supported:
                            failed_metrics.append(e.metric)
                        elif direction == MetricDirection.LOWER_IS_BETTER and e.candidate_value > e.baseline_value and e.statistically_supported:
                            failed_metrics.append(e.metric)

            elif failed_region.failure_type == "GENERALIZATION_FAILURE":
                # Generalization failures usually involve holdout/regression metrics.
                # If they are in observed_effects, we log them. Often they aren't in optimization effects.
                pass

            # Find the explored configuration for execution provenance
            explored = next((ex for ex in research_state.explored_configurations if ex.run_id == failed_region.run_id), None)
            dataset_version = explored.dataset_version if explored else None
            execution_provenance = explored.execution_provenance if explored else None

            entry = FailureAtlasEntry(
                canonical_configuration=failed_region.canonical_configuration,
                fingerprint=fp,
                experiment_id=failed_region.experiment_id,
                run_id=failed_region.run_id,
                failure_type=failed_region.failure_type,
                reason=failed_region.reason,
                failed_metrics=sorted(failed_metrics),
                failed_constraints=sorted(failed_constraints),
                observed_metric_values=observed_values,
                policy_snapshot=research_state.policy_snapshot,
                dataset_version=dataset_version,
                execution_provenance=execution_provenance
            )

            # Deterministic conflict resolution for same canonical fingerprint
            if fp not in entries:
                entries[fp] = entry
            else:
                # If it already exists, tie-break by lexicographically smaller run_id
                if entry.run_id < entries[fp].run_id:
                    entries[fp] = entry

        # Sort final entries deterministically by fingerprint
        final_entries = [entries[fp] for fp in sorted(entries.keys())]

        return FailureAtlas(entries=final_entries)
