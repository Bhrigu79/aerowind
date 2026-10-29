"""
AEROWIND — Session Orchestrator

Manages the outer research loop:
  - Initial objective satisfaction check (before first iteration)
  - Stop condition evaluation after every iteration
  - Delegates individual iterations to ResearchOrchestrator
  - Maps SEARCH_SPACE_EXHAUSTED from the orchestrator to session termination
"""

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import ResearchSession, Project, Experiment, Constraint, MetricResult, ExperimentRun
from app.domain.types import SessionState, StopReason, DecisionResult
from app.gateway.gateway import ModelGateway
from app.services.orchestrator import ResearchOrchestrator
from app.services.memory import ResearchMemoryService
from app.services.progress import ObjectiveProgressService

from app.services.runner import ExperimentRunner


class SessionOrchestrator:
    def __init__(self, gateway: ModelGateway, runner: ExperimentRunner = None):
        self.gateway = gateway
        self.orchestrator = ResearchOrchestrator(gateway, runner=runner)

    async def _update_best_known(self, session: AsyncSession, research_session: ResearchSession):
        from sqlalchemy.orm import selectinload
        stmt = select(Experiment).options(selectinload(Experiment.plan)).where(
            Experiment.session_id == research_session.id,
            Experiment.adopted == True
        ).order_by(Experiment.created_at.desc())
        res = await session.execute(stmt)
        best_exp = res.scalars().first()
        if best_exp:
            research_session.current_best_experiment_id = best_exp.id
            if best_exp.plan:
                research_session.current_best_variant_id = best_exp.plan.candidate_variant_id

    async def _check_stop_conditions(
        self, session: AsyncSession, research_session: ResearchSession
    ) -> StopReason | None:
        if research_session.iteration_count >= research_session.max_iterations:
            return StopReason.MAX_ITERATIONS
        if research_session.experiment_count >= research_session.max_experiments:
            return StopReason.MAX_EXPERIMENTS

        stmt = select(Constraint).where(Constraint.project_id == research_session.project_id)
        constraints = (await session.execute(stmt)).scalars().all()

        # Check if objective satisfied using the best experiment's metrics
        if research_session.current_best_experiment_id:
            from sqlalchemy.orm import selectinload
            stmt_exp = (
                select(Experiment)
                .options(selectinload(Experiment.runs).selectinload(ExperimentRun.variant))
                .where(Experiment.id == research_session.current_best_experiment_id)
            )
            exp = (await session.execute(stmt_exp)).scalars().first()
            if exp and exp.runs:
                cand_run = next((r for r in exp.runs if not r.variant.is_baseline), None)
                if cand_run:
                    stmt_metrics = select(MetricResult).where(MetricResult.run_id == cand_run.id)
                    metrics = (await session.execute(stmt_metrics)).scalars().all()
                    progress = ObjectiveProgressService.calculate_progress(constraints, [], metrics)
                    if progress["all_passed"]:
                        return StopReason.OBJECTIVE_SATISFIED

        return None

    async def _check_initial_objective_satisfaction(
        self, session: AsyncSession, research_session: ResearchSession
    ) -> bool:
        """
        Before the first iteration, check whether the project baseline already
        satisfies all constraints.  If so, stop immediately.
        """
        stmt = select(Constraint).where(Constraint.project_id == research_session.project_id)
        constraints = (await session.execute(stmt)).scalars().all()
        if not constraints:
            return False  # No constraints → nothing to satisfy

        # Look for existing candidate metrics from any adopted experiment
        stmt_exp = select(Experiment).where(
            Experiment.project_id == research_session.project_id,
            Experiment.adopted == True,
        ).order_by(Experiment.created_at.desc())
        best_exp = (await session.execute(stmt_exp)).scalars().first()

        if not best_exp:
            return False  # No prior experiments — cannot claim satisfied

        from sqlalchemy.orm import selectinload
        stmt_run = select(ExperimentRun).where(
            ExperimentRun.experiment_id == best_exp.id
        )
        runs = (await session.execute(stmt_run)).scalars().all()
        cand_run = next(
            (r for r in runs if r.variant_id and not getattr(r.variant, 'is_baseline', True)),
            None
        )
        if not cand_run:
            return False

        stmt_metrics = select(MetricResult).where(MetricResult.run_id == cand_run.id)
        metrics = (await session.execute(stmt_metrics)).scalars().all()
        progress = ObjectiveProgressService.calculate_progress(constraints, [], metrics)
        return progress["all_passed"]

    async def execute_session(self, session: AsyncSession, session_id: str):
        rs = await session.get(ResearchSession, session_id)
        if not rs:
            raise ValueError("Research Session not found")

        rs.status = SessionState.RUNNING.value
        await session.commit()

        project = await session.get(Project, rs.project_id)

        # ── Initial objective satisfaction check ────────────────────────────
        if await self._check_initial_objective_satisfaction(session, rs):
            rs.status = SessionState.COMPLETED.value
            rs.termination_reason = StopReason.OBJECTIVE_SATISFIED.value
            await session.commit()
            return

        while True:
            # ── Stop condition check ──────────────────────────────────────────
            stop_reason = await self._check_stop_conditions(session, rs)
            if stop_reason:
                rs.status = SessionState.COMPLETED.value
                rs.termination_reason = stop_reason.value
                await session.commit()
                break

            rs.iteration_count += 1
            await session.commit()

            try:
                exp = await self._execute_single_iteration(session, rs, project)

                rs.experiment_count += 1
                if exp.error_message or exp.status in ("failed", "search_space_exhausted"):
                    rs.failed_experiment_count += 1

                # Search space exhausted — terminate gracefully
                if exp.status == "search_space_exhausted":
                    rs.status = SessionState.COMPLETED.value
                    rs.termination_reason = StopReason.SEARCH_SPACE_EXHAUSTED.value
                    await session.commit()
                    break

                await self._update_best_known(session, rs)
                await session.commit()

                # Immediate check for objective satisfaction
                stop_reason = await self._check_stop_conditions(session, rs)
                if stop_reason == StopReason.OBJECTIVE_SATISFIED:
                    rs.status = SessionState.COMPLETED.value
                    rs.termination_reason = stop_reason.value
                    await session.commit()
                    break

            except Exception as e:
                import traceback
                traceback.print_exc()
                rs.status = SessionState.FAILED.value
                rs.termination_reason = StopReason.EXECUTION_FAILURE.value
                await session.commit()
                break

    async def _execute_single_iteration(
        self, session: AsyncSession, rs: ResearchSession, project: Project
    ) -> Experiment:
        exp = await self.orchestrator.execute_iteration(session, project.id)
        exp.session_id = rs.id
        await session.flush()
        return exp
