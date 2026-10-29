import math
from typing import List, Dict, Set
from app.schemas.research import ResearchState, ParetoFrontier
from app.domain.types import MetricDirection

class ParetoFrontierService:
    @staticmethod
    def build_frontier(
        research_state: ResearchState,
        objective_metrics: List[str],
        metric_directions: Dict[str, MetricDirection]
    ) -> ParetoFrontier:

        # FIX 3: Explicit tie-breaker for duplicate fingerprints
        fingerprint_to_run: Dict[str, dict] = {}
        for explored in research_state.explored_configurations:
            if explored.fingerprint in research_state.feasible_configurations:
                fp = explored.fingerprint
                # Deterministic tie-breaker: if canonical fingerprint appears multiple times, use lexicographically smallest run_id
                if fp not in fingerprint_to_run or explored.run_id < fingerprint_to_run[fp]["run_id"]:
                    fingerprint_to_run[fp] = {
                        "exp_id": explored.experiment_id,
                        "run_id": explored.run_id
                    }

        # FIX 1: Deterministic duplicate resolution (fail closed on conflicting aggregated means)
        run_metrics: Dict[str, Dict[str, float]] = {}
        excluded_runs = set()

        for effect in research_state.observed_effects:
            run_id = effect.source_run_id
            cv = effect.candidate_value
            if cv is not None:
                if run_id not in run_metrics:
                    run_metrics[run_id] = {}

                # If we already have a value for this metric on this run
                if effect.metric in run_metrics[run_id]:
                    # They must be mathematically identical since they are authoritative aggregates
                    # If they conflict, the evidence is corrupt -> fail closed
                    if not math.isclose(run_metrics[run_id][effect.metric], cv, rel_tol=1e-9):
                        excluded_runs.add(run_id)
                else:
                    run_metrics[run_id][effect.metric] = cv

        # 2. Filter feasible configs that have ALL required objective metrics AND finite values
        eligible_fingerprints = []
        metric_values: Dict[str, Dict[str, float]] = {}
        source_exp_ids: Dict[str, str] = {}
        source_run_ids: Dict[str, str] = {}

        for fp, ids in fingerprint_to_run.items():
            r_id = ids["run_id"]
            if r_id in excluded_runs:
                continue

            if r_id in run_metrics:
                m_dict = run_metrics[r_id]
                has_all_valid = True
                for om in objective_metrics:
                    if om not in m_dict:
                        has_all_valid = False
                        break

                    # FIX 2: Explicitly exclude non-finite values from eligibility
                    if not math.isfinite(m_dict[om]):
                        has_all_valid = False
                        break

                if has_all_valid:
                    eligible_fingerprints.append(fp)
                    metric_values[fp] = {om: m_dict[om] for om in objective_metrics}
                    source_exp_ids[fp] = ids["exp_id"]
                    source_run_ids[fp] = r_id

        # 3. Compute Dominance
        dominance_relationships: Dict[str, List[str]] = {fp: [] for fp in eligible_fingerprints}
        dominated_set: Set[str] = set()

        # Sort eligible fingerprints for determinism
        eligible_fingerprints.sort()

        for i, fp_A in enumerate(eligible_fingerprints):
            for j, fp_B in enumerate(eligible_fingerprints):
                if i == j:
                    continue

                vals_A = metric_values[fp_A]
                vals_B = metric_values[fp_B]

                # Check if A dominates B
                at_least_as_good = True
                strictly_better = False

                for om in objective_metrics:
                    vA = vals_A[om]
                    vB = vals_B[om]

                    direction = metric_directions.get(om, MetricDirection.HIGHER_IS_BETTER)

                    if direction == MetricDirection.HIGHER_IS_BETTER:
                        if vA < vB:
                            at_least_as_good = False
                            break
                        if vA > vB:
                            strictly_better = True
                    else: # LOWER_IS_BETTER
                        if vA > vB:
                            at_least_as_good = False
                            break
                        if vA < vB:
                            strictly_better = True

                if at_least_as_good and strictly_better:
                    dominance_relationships[fp_A].append(fp_B)
                    dominated_set.add(fp_B)

        # 4. Determine Frontier
        frontier_fingerprints = sorted(list(set(eligible_fingerprints) - dominated_set))
        dominated_fingerprints = sorted(list(dominated_set))

        for fp in dominance_relationships:
            dominance_relationships[fp].sort()

        # FIX 4: Set current_best metadata without mutating ResearchState
        current_best = research_state.current_best_fingerprint
        current_best_is_dominated = None
        if current_best:
            if current_best in dominated_fingerprints:
                current_best_is_dominated = True
            elif current_best in frontier_fingerprints:
                current_best_is_dominated = False

        return ParetoFrontier(
            objective_metrics=sorted(objective_metrics),
            optimization_directions=metric_directions,
            frontier_fingerprints=frontier_fingerprints,
            dominated_fingerprints=dominated_fingerprints,
            dominance_relationships=dominance_relationships,
            metric_values=metric_values,
            source_experiment_ids=source_exp_ids,
            source_run_ids=source_run_ids,
            current_best_fingerprint=current_best,
            current_best_is_dominated=current_best_is_dominated
        )
