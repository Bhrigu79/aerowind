"""
AEROWIND — Research Strategy Service

Determines which configuration dimension to explore next based on:
  1. The largest unsatisfied constraint gap.
  2. Which dimensions have already been explored (from *completed* experiments only).

INVARIANT:
  - selected_dimension is ALWAYS a specific, recognised dimension string.
  - There is NO fallback to "hyperparameter_tuning" or any other bypass.
  - When all dimensions are exhausted, returns selected_dimension=None
    signalling SEARCH_SPACE_EXHAUSTED to the orchestrator.
  - Only actually-executed experiments (status="completed") contribute to
    explored_dimensions.  Failed validation/strategy experiments do NOT.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import Project, Constraint, MetricResult, ExperimentVariant, Experiment
from app.services.progress import ObjectiveProgressService
from app.core.config_validator import KNOWN_DIMENSIONS


class ResearchStrategyService:

    @staticmethod
    def validate_strategy_change(baseline_config: dict, candidate_config: dict, selected_dimension: str) -> bool:
        """
        Deterministically verifies if the selected dimension was materially changed.

        NOTE: selected_dimension is NEVER "hyperparameter_tuning" — that
        bypass has been removed.  The caller must not pass None here.
        """
        def get_nested(d: dict, path: str):
            keys = path.split('.')
            val = d
            for k in keys:
                if isinstance(val, dict) and k in val:
                    val = val[k]
                else:
                    return None
            return val

        from app.core.config_validator import ConfigurationValidator
        norm_base = ConfigurationValidator.normalize(baseline_config)
        norm_cand = ConfigurationValidator.normalize(candidate_config)

        base_val = get_nested(norm_base, selected_dimension)
        cand_val = get_nested(norm_cand, selected_dimension)

        # If both are None, the dimension was not added or modified
        if base_val is None and cand_val is None:
            return False

        return base_val != cand_val

    @staticmethod
    async def determine_strategy(
        session: AsyncSession,
        project_id: str,
        constraints: list[Constraint],
        current_metrics: list[MetricResult]
    ) -> dict:
        """
        Determines the next deterministic research strategy based on objective
        progress and explored dimensions.

        Returns a dict with:
          selected_dimension: str | None
            None  => all dimensions exhausted; orchestrator must stop with
                     SEARCH_SPACE_EXHAUSTED.
          reason: str — human-readable explanation.
          ... (other progress fields)
        """
        # STEP 1: Identify the largest unsatisfied constraint gap
        progress = ObjectiveProgressService.calculate_progress(constraints, [], current_metrics)

        largest_gap = 0.0
        target_constraint_name = "general"
        target_val = 0.0
        current_val = 0.0

        constraint_map = {c.metric_name: c for c in constraints}

        for metric_name, m_prog in progress.get("metrics_progress", {}).items():
            if not m_prog.get("passed", False):
                req = m_prog.get("target")
                cur = m_prog.get("current")

                if req is None and metric_name in constraint_map:
                    req = constraint_map[metric_name].required_value
                if cur is None:
                    gap = 1.0
                    cur = 0.0
                elif req != 0:
                    gap = abs(req - cur) / abs(req)
                else:
                    gap = 1.0

                if gap > largest_gap:
                    largest_gap = gap
                    target_constraint_name = metric_name
                    target_val = req if req is not None else 0.0
                    current_val = cur

        # STEP 2: Collect explored dimensions — ONLY from completed experiments.
        # Validation failures and strategy enforcement failures do NOT count
        # as explored dimensions because the configuration was never executed.
        stmt_completed_exps = (
            select(Experiment)
            .where(
                Experiment.project_id == project_id,
                Experiment.status == "completed"
            )
        )
        completed_exp_ids = [
            e.id for e in (await session.execute(stmt_completed_exps)).scalars().all()
        ]

        explored_dimensions: set[str] = set()

        if completed_exp_ids:
            # Fetch baseline variants for this project
            stmt_baselines = select(ExperimentVariant).where(
                ExperimentVariant.project_id == project_id,
                ExperimentVariant.is_baseline == True
            )
            baselines = (await session.execute(stmt_baselines)).scalars().all()
            base_config = baselines[0].system_configuration if baselines else {}

            # Fetch candidate variants only linked to completed experiments
            stmt_candidates = select(ExperimentVariant).where(
                ExperimentVariant.project_id == project_id,
                ExperimentVariant.is_baseline == False
            )
            all_candidates = (await session.execute(stmt_candidates)).scalars().all()

            # We need to know which variant IDs belong to completed experiments.
            # This requires checking ExperimentPlan.candidate_variant_id for completed exps.
            from app.db.models import ExperimentPlan
            stmt_plans = select(ExperimentPlan).where(
                ExperimentPlan.experiment_id.in_(completed_exp_ids)
            )
            plans = (await session.execute(stmt_plans)).scalars().all()
            completed_candidate_variant_ids = {p.candidate_variant_id for p in plans if p.candidate_variant_id}

            for c in all_candidates:
                if c.id not in completed_candidate_variant_ids:
                    continue
                cand_config = c.system_configuration or {}
                for k, v in cand_config.items():
                    if k in KNOWN_DIMENSIONS and base_config.get(k) != v:
                        explored_dimensions.add(k)

        # STEP 3: Map constraint target to candidate dimensions
        quality_dimensions   = ["prompt_strategy", "few_shot_count", "retrieval_enabled", "pipeline_mode", "model", "temperature", "chain_of_thought", "max_tokens"]
        latency_dimensions   = ["retrieval_enabled", "pipeline_mode", "model", "max_tokens", "chain_of_thought"]
        cost_dimensions      = ["model", "max_tokens", "retrieval_enabled", "pipeline_mode", "chain_of_thought"]
        error_dimensions     = ["temperature", "prompt_strategy"]

        if "quality" in target_constraint_name:
            target_list = quality_dimensions
        elif "latency" in target_constraint_name:
            target_list = latency_dimensions
        elif "cost" in target_constraint_name:
            target_list = cost_dimensions
        elif "error" in target_constraint_name:
            target_list = error_dimensions
        else:
            target_list = sorted(list(KNOWN_DIMENSIONS))

        unexplored_in_target = [d for d in target_list if d not in explored_dimensions]
        unexplored_all = [d for d in sorted(KNOWN_DIMENSIONS) if d not in explored_dimensions]

        if unexplored_in_target:
            selected_dimension: str | None = unexplored_in_target[0]
            reason = (
                f"{target_constraint_name.capitalize()} is the largest remaining objective gap "
                f"and '{selected_dimension}' has not yet been explored but can affect it."
            )
        elif unexplored_all:
            selected_dimension = unexplored_all[0]
            reason = (
                f"{target_constraint_name.capitalize()} needs improvement, but specific dimensions "
                f"are exhausted. Exploring '{selected_dimension}'."
            )
        else:
            # All known dimensions have been explored and constraints are still failing.
            # Signal the orchestrator to terminate — no unrestricted LLM fallback.
            selected_dimension = None
            reason = (
                f"All supported search-space dimensions have been explored. "
                f"Constraint '{target_constraint_name}' remains unsatisfied. "
                f"Terminating with SEARCH_SPACE_EXHAUSTED."
            )

        return {
            "target_constraint": target_constraint_name,
            "current_value": current_val,
            "target": target_val,
            "gap": abs(target_val - current_val),
            "explored_dimensions": sorted(explored_dimensions),
            "unexplored_dimensions": list(unexplored_all),
            "selected_dimension": selected_dimension,
            "reason": reason,
        }
