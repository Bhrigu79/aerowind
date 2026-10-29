from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import Experiment, Project, Evidence, Decision, ExperimentPlan, ExperimentRun, Constraint

class CertificateService:
    @staticmethod
    async def generate_certificate(session: AsyncSession, experiment_id: str) -> Dict[str, Any]:
        """
        Generates an exportable 'AEROWIND Optimization Certificate' ONLY from persisted evidence.
        It must never say 'globally optimal', 'best possible', or equivalent.
        """
        exp = await session.get(Experiment, experiment_id)
        if not exp:
            raise ValueError(f"Experiment {experiment_id} not found")

        project = await session.get(Project, exp.project_id)
        if not project:
            raise ValueError(f"Project {exp.project_id} not found")

        # Get evidence and decisions
        stmt_evidence = select(Evidence).where(Evidence.experiment_id == experiment_id)
        evidence = (await session.execute(stmt_evidence)).scalars().first()

        stmt_decision = select(Decision).where(Decision.experiment_id == experiment_id)
        decision = (await session.execute(stmt_decision)).scalars().first()

        # Get plan
        stmt_plan = select(ExperimentPlan).where(ExperimentPlan.experiment_id == experiment_id)
        plan = (await session.execute(stmt_plan)).scalars().first()

        # Get runs to extract provenance and stats
        stmt_run = select(ExperimentRun).where(ExperimentRun.experiment_id == experiment_id)
        runs = (await session.execute(stmt_run)).scalars().all()

        # Get project constraints
        stmt_constraints = select(Constraint).where(Constraint.project_id == project.id)
        db_constraints = (await session.execute(stmt_constraints)).scalars().all()
        constraints_list = [
            {"metric_name": c.metric_name, "operator": c.operator, "required_value": c.required_value}
            for c in db_constraints
        ]

        # Extract diffs
        baseline_config = plan.baseline_variant.system_configuration if plan and plan.baseline_variant else {}
        candidate_config = plan.candidate_variant.system_configuration if plan and plan.candidate_variant else {}

        config_diff = {}
        for k, v in candidate_config.items():
            b_v = baseline_config.get(k)
            if b_v != v:
                config_diff[k] = {"baseline": b_v, "candidate": v}

        cand_run = next((r for r in runs if not getattr(r.variant, 'is_baseline', True)), None)
        baseline_run = next((r for r in runs if getattr(r.variant, 'is_baseline', False)), None)

        dataset_version = cand_run.dataset_version if cand_run else None
        dataset_hash = cand_run.dataset_hash if cand_run else None
        evaluation_policy = cand_run.evaluation_policy_snapshot if cand_run else {}

        execution_provenance = cand_run.execution_provenance if cand_run else "UNKNOWN"

        provider = cand_run.execution_metadata.get("provider", "unknown") if cand_run and cand_run.execution_metadata else "unknown"
        model = cand_run.execution_metadata.get("model", "unknown") if cand_run and cand_run.execution_metadata else "unknown"

        trial_count = len(cand_run.trials) if cand_run and hasattr(cand_run, "trials") and cand_run.trials else 1

        metric_observations = []
        aggregate_stats = {}
        if cand_run:
             # get metrics from cand_run
             from app.db.models import MetricResult
             stmt_metrics = select(MetricResult).where(MetricResult.run_id == cand_run.id)
             cand_metrics = (await session.execute(stmt_metrics)).scalars().all()

             for m in cand_metrics:
                 metric_observations.append({
                     "name": m.metric_name,
                     "value": m.value,
                     "unit": m.unit,
                     "direction": m.direction,
                     "sample_size": m.sample_size
                 })
                 aggregate_stats[m.metric_name] = m.value

        decision_text = decision.result if decision else "UNKNOWN"
        failure_reasons = []
        if decision_text == "REJECT":
            failure_reasons.append(decision.rationale if decision else "No rationale provided")

        cert = {
            "title": "AEROWIND Optimization Certificate",
            "statement": "Best retained configuration under the evaluated objective constraints and research policy.",
            "objective": project.objective,
            "constraints": constraints_list,
            "baseline_configuration": baseline_config,
            "candidate_configuration": candidate_config,
            "deterministic_config_diff": config_diff,
            "dataset": {
                "version": dataset_version,
                "hash": dataset_hash
            },
            "trial_count": trial_count,
            "metric_observations": metric_observations,
            "aggregate_statistics": aggregate_stats,
            "uncertainty_evidence": evidence.calculations if evidence else {},
            "decision": decision_text,
            "failure_reasons": failure_reasons,
            "execution_provenance": execution_provenance,
            "provider": provider,
            "model": model,
            "timestamp": exp.completed_at.isoformat() if exp.completed_at else (exp.created_at.isoformat() if exp.created_at else None),
            "research_policy_snapshot": evaluation_policy,
            "reproducibility_reference": f"experiment_id:{experiment_id}"
        }

        return cert
