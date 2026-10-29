import math
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List
from sqlalchemy import select

from app.db.models import ExperimentRun, ExperimentTrial, MetricResult
from app.schemas.evaluation import EvaluationPolicy, MetricObservationSet, MetricStatistics
from app.services.runner import ExperimentRunner
from app.services.statistics import StatisticalEngine

class TrialSessionAdapter:
    """Explicitly binds metrics created during a trial's exact execution window to that trial."""
    def __init__(self, session: AsyncSession, trial: ExperimentTrial):
        self._session = session
        self._trial = trial

    def add(self, instance: Any) -> None:
        if isinstance(instance, MetricResult):
            if instance.run_id != self._trial.run_id:
                raise ValueError(f"MetricResult run_id {instance.run_id} does not match trial run_id {self._trial.run_id}")
            instance.trial_id = self._trial.id
        self._session.add(instance)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

class TrialExecutionFailure(Exception):
    pass

class TrialExecutionService:

    @staticmethod
    async def execute_trials(
        session: AsyncSession,
        run: ExperimentRun,
        runner: ExperimentRunner,
        spec: Any = None,
        **kwargs
    ) -> Dict[str, MetricStatistics]:

        policy_dict = run.evaluation_policy_snapshot
        try:
            policy = EvaluationPolicy(**policy_dict) if policy_dict else EvaluationPolicy()
        except ValueError as e:
            run.success = False
            run.error_info = f"Invalid EvaluationPolicy: {e}"
            run.status = "failed"
            raise TrialExecutionFailure(run.error_info)

        target_successes = policy.min_trials
        max_attempts = policy.max_trials
        allowed_failures = math.floor(max_attempts * policy.failure_tolerance_ratio)

        failures = 0
        successes = 0
        attempts = 0

        run.started_at = datetime.utcnow()
        run.status = "running"

        metrics_collector: Dict[str, List[float]] = {}
        raw_obs_collector: Dict[str, List[List[float]]] = {}

        while attempts < max_attempts and successes < target_successes:
            trial = ExperimentTrial(
                run_id=run.id,
                trial_index=attempts,
                status="running",
                execution_provenance=run.execution_provenance,
                started_at=datetime.utcnow()
            )
            session.add(trial)
            await session.flush()

            adapter = TrialSessionAdapter(session, trial)

            try:
                # runner receives the adapter, ensuring exact explicit capture instead of broad implicit scans
                await runner.execute(adapter, run, spec=spec, **kwargs)
                await session.flush()

                if hasattr(run, 'success') and run.success is False:
                    raise Exception(run.error_info or "Runner marked run as failed")

                trial.status = "completed"
                trial.completed_at = datetime.utcnow()
                successes += 1

                # Fetch metrics explicitly tied to this trial
                trial_metrics = (await session.execute(
                    select(MetricResult).where(MetricResult.trial_id == trial.id)
                )).scalars().all()

                for tm in trial_metrics:
                    if tm.metric_name not in metrics_collector:
                        metrics_collector[tm.metric_name] = []
                        raw_obs_collector[tm.metric_name] = []
                    metrics_collector[tm.metric_name].append(tm.value)

                    # Store raw_observations strictly per-trial to guarantee provenance boundary
                    raw = getattr(tm, 'raw_observations', []) or []
                    raw_obs_collector[tm.metric_name].append(raw)

            except Exception as e:
                trial.status = "failed"
                trial.completed_at = datetime.utcnow()
                trial.error_info = str(e)
                failures += 1

                if failures > allowed_failures:
                    break

                remaining_attempts = max_attempts - (attempts + 1)
                if successes + remaining_attempts < target_successes:
                    break
            finally:
                attempts += 1

        if successes < target_successes:
            run.success = False
            if failures > allowed_failures:
                run.error_info = f"Exceeded failure tolerance ({failures} > {allowed_failures})"
            else:
                run.error_info = f"Failed to reach target successes ({successes} < {target_successes})"
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            raise TrialExecutionFailure(run.error_info)

        run.success = True
        run.status = "completed"
        run.error_info = None
        run.completed_at = datetime.utcnow()

        aggregated_evidence: Dict[str, MetricStatistics] = {}
        for metric_name, values in metrics_collector.items():
            raw_obs = raw_obs_collector[metric_name]
            obs_set = MetricObservationSet(
                values=values,
                raw_observations=raw_obs if any(r for r in raw_obs) else None,
                is_legacy=False
            )
            stats = StatisticalEngine.aggregate_metrics(obs_set)
            aggregated_evidence[metric_name] = stats

        return aggregated_evidence
