from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.models import Project, Hypothesis, Experiment, ExperimentPlan, Decision

class ResearchMemoryService:
    @staticmethod
    async def get_project_memory(session: AsyncSession, project_id: str) -> dict:
        from app.db.models import ExperimentVariant

        # 1. Fetch current best (baseline)
        stmt_best = select(ExperimentVariant).where(
            ExperimentVariant.project_id == project_id,
            ExperimentVariant.is_baseline == True
        ).order_by(ExperimentVariant.created_at.desc()).limit(1)
        best_variant = (await session.execute(stmt_best)).scalar_one_or_none()
        current_best = best_variant.system_configuration if best_variant else {}

        # 2. Fetch past experiments
        stmt_exp = select(Experiment).options(
            selectinload(Experiment.plan).selectinload(ExperimentPlan.candidate_variant),
            selectinload(Experiment.plan).selectinload(ExperimentPlan.baseline_variant),
            selectinload(Experiment.decisions)
        ).where(
            Experiment.project_id == project_id,
            Experiment.experiment_type != "holdout_validation"
        ).order_by(Experiment.created_at.desc()).limit(10)

        res_exp = await session.execute(stmt_exp)
        exps = res_exp.scalars().all()

        previous_experiments = []
        successful_patterns = []
        failed_patterns = []
        tested_configs = []

        for exp in exps:
            plan = exp.plan
            decision = exp.decisions[0] if exp.decisions else None

            exp_data = {
                "name": exp.name,
                "hypothesis": exp.candidate_description,
                "adopted": exp.adopted,
            }
            cand_config = plan.candidate_variant.system_configuration if plan and plan.candidate_variant else None
            if cand_config:
                tested_configs.append(cand_config)

            if decision:
                exp_data["decision"] = decision.result
                exp_data["reason"] = decision.rationale

            previous_experiments.append(exp_data)

            if exp.adopted:
                successful_patterns.append(exp.candidate_description)
            elif decision and decision.result == "reject":
                failed_patterns.append(exp.candidate_description)
                if cand_config:
                    failed_patterns.append(f"Rejected config: {cand_config}")

        return {
            "current_best_configuration": current_best,
            "tested_configurations": tested_configs,
            "previous_experiments": previous_experiments,
            "successful_patterns": successful_patterns,
            "failed_patterns": failed_patterns,
        }

    @staticmethod
    async def is_duplicate_candidate(session: AsyncSession, project_id: str, candidate_config: dict) -> bool:
        """
        Detects if the proposed candidate config is identical to any previously evaluated variant.
        For simplicity, we check string representation of config.
        """
        from app.db.models import ExperimentVariant
        from app.core.config_validator import ConfigurationValidator
        import json

        normalized_cand = ConfigurationValidator.normalize(candidate_config)
        config_str = json.dumps(normalized_cand, sort_keys=True)

        stmt = select(ExperimentVariant).where(ExperimentVariant.project_id == project_id)
        res = await session.execute(stmt)
        variants = res.scalars().all()

        for v in variants:
            if not v.is_baseline:
                normalized_v = ConfigurationValidator.normalize(v.system_configuration)
                v_config_str = json.dumps(normalized_v, sort_keys=True)
                if config_str == v_config_str:
                    return True
        return False
