from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Evidence, Experiment, ExperimentRun, MetricResult
from typing import List

class EvidenceService:
    @staticmethod
    async def create_evidence(
        session: AsyncSession,
        experiment: Experiment,
        run: ExperimentRun,
        baseline_metrics: List[MetricResult],
        candidate_metrics: List[MetricResult],
        claim: str,
        conclusion: str
    ) -> Evidence:
        baseline_vals = {m.metric_name: m.value for m in baseline_metrics}
        candidate_vals = {m.metric_name: m.value for m in candidate_metrics}

        calculations = {}
        for k, v in candidate_vals.items():
            if k in baseline_vals and baseline_vals[k] != 0:
                diff = v - baseline_vals[k]
                pct = (diff / baseline_vals[k]) * 100
                calculations[k] = {"diff": diff, "pct_change": pct}

        evidence = Evidence(
            experiment_id=experiment.id,
            claim=claim,
            baseline_values=baseline_vals,
            candidate_values=candidate_vals,
            calculations=calculations,
            conclusion=conclusion
        )
        session.add(evidence)
        return evidence
