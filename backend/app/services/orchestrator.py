"""
AEROWIND — Research Orchestrator

Executes a single autonomous research iteration:

  1. Fetch baseline configuration.
  2. Collect memory + constraints.
  3. Deterministic strategy selection.
     → If selected_dimension is None: SEARCH_SPACE_EXHAUSTED.
  4. LLM: generate hypothesis.
  5. LLM: design experiment (candidate configuration).
  6. Strategy enforcement (deterministic, up to 3 retries).
  7. Configuration validation (type + value bounds).
  8. Baseline equality check (candidate must differ from baseline).
  9. Duplicate check (candidate must not repeat a prior candidate).
 10. Run baseline + candidate.
 11. Evaluate constraints.
 12. Decide RETAIN / REJECT / INCONCLUSIVE.
 13. Store evidence.

INVARIANT: proposed config == validated config == executed config.
There is NO silent coercion or defaulting.
"""

import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import (
    Project, Hypothesis, Experiment, ExperimentPlan, ExperimentVariant,
    ExperimentRun, Constraint, MetricResult, Evidence, Decision
)
from app.domain.types import ExperimentState, DecisionResult
from app.gateway.gateway import ModelGateway
from app.agents.research import PlannerAgent, HypothesisAgent, ExperimentDesignerAgent, ResearcherAgent
from app.services.state import ExperimentStateMachine
from app.services.runner import ExperimentRunner, SyntheticExperimentRunner
from app.services.constraints import ConstraintEngine
from app.services.decision import DecisionEngine
from app.services.evidence import EvidenceService
from app.core.config_validator import ConfigurationValidator


def _configs_are_equal(a: dict, b: dict) -> bool:
    """Canonical structural equality: normalizes defaults then compares JSON."""
    from app.core.config_validator import ConfigurationValidator
    norm_a = ConfigurationValidator.normalize(a)
    norm_b = ConfigurationValidator.normalize(b)
    return json.dumps(norm_a, sort_keys=True) == json.dumps(norm_b, sort_keys=True)


class ResearchOrchestrator:
    def __init__(self, gateway: ModelGateway, runner: ExperimentRunner = None):
        self.gateway = gateway
        self.planner = PlannerAgent(gateway)
        self.hypothesis_agent = HypothesisAgent(gateway)
        self.designer = ExperimentDesignerAgent(gateway)
        self.researcher = ResearcherAgent(gateway)
        self.runner = runner or SyntheticExperimentRunner()

    def _make_failed_experiment(self, project_id: str, name: str, error_message: str,
                                 candidate_description: str = "", strategy_reason: dict = None) -> Experiment:
        """Helper: create a pre-built failed experiment (not yet added to session)."""
        return Experiment(
            project_id=project_id,
            name=name,
            experiment_type="autonomous",
            status="failed",
            error_message=error_message,
            candidate_description=candidate_description,
            strategy_reason=strategy_reason,
        )

    async def execute_iteration(self, session: AsyncSession, project_id: str,
                                 pre_hyp_schema=None, pre_plan_schema=None) -> Experiment:
        project = await session.get(Project, project_id)
        if not project:
            raise ValueError("Project not found")

        # ── Step 1: Fetch baseline configuration ─────────────────────────────
        baseline_config = {}
        stmt_best = select(Experiment).where(
            Experiment.project_id == project_id,
            Experiment.adopted == True
        ).order_by(Experiment.created_at.desc())
        best_exp = (await session.execute(stmt_best)).scalars().first()
        cand_run = None
        if best_exp:
            from sqlalchemy.orm import selectinload
            stmt_run = select(ExperimentRun).options(
                selectinload(ExperimentRun.variant)
            ).where(ExperimentRun.experiment_id == best_exp.id)
            runs = (await session.execute(stmt_run)).scalars().all()
            cand_run = next((r for r in runs if r.variant and not r.variant.is_baseline), None)
            if cand_run:
                baseline_config = cand_run.variant.system_configuration
        elif project.target_system_description:
            try:
                baseline_config = json.loads(project.target_system_description)
            except json.JSONDecodeError:
                pass

        if not pre_hyp_schema or not pre_plan_schema:
            from app.services.progress import ObjectiveProgressService
            from app.services.memory import ResearchMemoryService
            from app.services.strategy import ResearchStrategyService

            memory = await ResearchMemoryService.get_project_memory(session, project_id)

            stmt = select(Constraint).where(Constraint.project_id == project_id)
            constraints = (await session.execute(stmt)).scalars().all()

            metrics = []
            if best_exp and cand_run:
                stmt_metrics = select(MetricResult).where(MetricResult.run_id == cand_run.id)
                metrics = (await session.execute(stmt_metrics)).scalars().all()

            strategy_record = await ResearchStrategyService.determine_strategy(
                session, project_id, constraints, metrics
            )

            # ── Step 3a: Search-space exhaustion check ──────────────────────
            if strategy_record["selected_dimension"] is None:
                exp = self._make_failed_experiment(
                    project_id=project_id,
                    name="Search Space Exhausted",
                    error_message=(
                        "All supported configuration dimensions have been explored and "
                        "constraints remain unsatisfied. "
                        f"Reason: {strategy_record['reason']}"
                    ),
                    strategy_reason=strategy_record,
                )
                # Use special status so the session loop can detect it
                exp.status = "search_space_exhausted"
                session.add(exp)
                await session.flush()
                return exp

            sel_dim = strategy_record["selected_dimension"]
            focus_area = (
                f"Focus strictly on optimizing the dimension: '{sel_dim}'. "
                f"The reason is: {strategy_record['reason']}"
            )

            # ── Step 4–6: LLM proposal + strategy enforcement (3 retries) ───
            max_retries = 3
            hyp_schema = None
            plan_schema = None

            for attempt in range(max_retries):
                hyp_schema = await self.hypothesis_agent.generate_hypothesis(
                    project, focus_area, memory=memory
                )
                plan_schema = await self.designer.design_experiment(
                    hyp_schema,
                    project.target_system_description or "",
                    baseline_config=baseline_config
                )

                is_valid_change = ResearchStrategyService.validate_strategy_change(
                    baseline_config, plan_schema.candidate_configuration, sel_dim
                )
                if not is_valid_change:
                    if attempt == max_retries - 1:
                        exp = self._make_failed_experiment(
                            project_id=project_id,
                            name="Strategy Enforcement Failed",
                            error_message=f"LLM repeatedly ignored strategy dimension '{sel_dim}'",
                            candidate_description=hyp_schema.candidate_description,
                            strategy_reason=strategy_record,
                        )
                        session.add(exp)
                        await session.flush()
                        return exp
                    continue
                break

            # ── Step 7: Configuration type/value validation ──────────────────
            validation_result = ConfigurationValidator.validate(plan_schema.candidate_configuration)
            if not validation_result.valid:
                exp = self._make_failed_experiment(
                    project_id=project_id,
                    name="Configuration Validation Failed",
                    error_message=(
                        f"Invalid candidate configuration: {validation_result.error_message}"
                    ),
                    candidate_description=hyp_schema.candidate_description,
                    strategy_reason=strategy_record,
                )
                session.add(exp)
                await session.flush()
                return exp

            # ── Step 8: Baseline equality check ─────────────────────────────
            if _configs_are_equal(plan_schema.candidate_configuration, baseline_config):
                exp = self._make_failed_experiment(
                    project_id=project_id,
                    name="Candidate Equals Baseline",
                    error_message=(
                        "Proposed candidate configuration is identical to the current baseline. "
                        "No experiment executed."
                    ),
                    candidate_description=hyp_schema.candidate_description,
                    strategy_reason=strategy_record,
                )
                session.add(exp)
                await session.flush()
                return exp

            # ── Step 9: Historical duplicate check ───────────────────────────
            from app.services.memory import ResearchMemoryService
            is_dup = await ResearchMemoryService.is_duplicate_candidate(
                session, project_id, plan_schema.candidate_configuration
            )
            if is_dup:
                exp = self._make_failed_experiment(
                    project_id=project_id,
                    name="Duplicate Candidate Detected",
                    error_message="Duplicate candidate configuration — already evaluated.",
                    candidate_description=hyp_schema.candidate_description,
                    strategy_reason=strategy_record,
                )
                session.add(exp)
                await session.flush()
                return exp

        else:
            hyp_schema = pre_hyp_schema
            plan_schema = pre_plan_schema
            focus_area = hyp_schema.target_metric or "Targeted optimization"
            strategy_record = None

            # Still validate pre-wired configs
            validation_result = ConfigurationValidator.validate(plan_schema.candidate_configuration)
            if not validation_result.valid:
                raise ValueError(
                    f"pre_plan_schema has invalid candidate_configuration: "
                    f"{validation_result.error_message}"
                )

        # ── Step 10: Persist hypothesis + variants + experiment ──────────────
        hypothesis = Hypothesis(
            project_id=project.id,
            statement=hyp_schema.claim,
            claim=hyp_schema.claim,
            expected_effect=hyp_schema.expected_effect,
            target_metric=hyp_schema.target_metric,
            expected_direction=hyp_schema.expected_direction,
            expected_magnitude=hyp_schema.expected_magnitude,
            confidence=hyp_schema.confidence,
            independent_variable=hyp_schema.independent_variable,
            control_description=hyp_schema.control_description,
            candidate_description=hyp_schema.candidate_description,
            risks=hyp_schema.risks,
            status="testing",
        )
        session.add(hypothesis)
        await session.flush()

        baseline_variant = ExperimentVariant(
            project_id=project.id,
            name="Baseline",
            is_baseline=True,
            system_configuration=baseline_config,
        )
        candidate_variant = ExperimentVariant(
            project_id=project.id,
            name="Candidate",
            is_baseline=False,
            system_configuration=plan_schema.candidate_configuration,
        )
        session.add(baseline_variant)
        session.add(candidate_variant)
        await session.flush()

        experiment = Experiment(
            project_id=project.id,
            hypothesis_id=hypothesis.id,
            name=f"Test: {focus_area[:50]}",
            experiment_type="autonomous",
            status=ExperimentState.DRAFT.value,
            candidate_description=hyp_schema.candidate_description,
            strategy_reason=strategy_record,
        )
        session.add(experiment)
        await session.flush()

        actual_changed = ConfigurationValidator.diff_effective_config(
            baseline_config, plan_schema.candidate_configuration
        )
        actual_held = [dim for dim in sorted(ConfigurationValidator.normalize({}).keys()) if dim not in actual_changed]

        plan = ExperimentPlan(
            experiment_id=experiment.id,
            hypothesis_summary=plan_schema.hypothesis_summary,
            baseline_variant_id=baseline_variant.id,
            candidate_variant_id=candidate_variant.id,
            changed_variables=actual_changed,
            held_constant_variables=actual_held,
            workload=plan_schema.workload,
            metrics_to_measure=plan_schema.metrics_to_measure,
            sample_size=plan_schema.sample_size,
            stop_conditions=plan_schema.stop_conditions,
            expected_result=plan_schema.expected_result,
        )
        session.add(plan)

        await ExperimentStateMachine.transition(session, experiment, ExperimentState.PLANNED)
        await ExperimentStateMachine.transition(session, experiment, ExperimentState.READY)
        await ExperimentStateMachine.transition(session, experiment, ExperimentState.RUNNING)
        await session.flush()

        # ── Determine runner_type string for provenance ───────────────────────
        runner_type_str = "synthetic"
        cls_name = self.runner.__class__.__name__
        if "RealAIBenchmarkRunner" in cls_name:
            runner_type_str = "real_ai"
        elif "NebiusExperimentRunner" in cls_name:
            runner_type_str = "nebius"

        # ── Step 10a: Baseline run ────────────────────────────────────────────
        baseline_run = ExperimentRun(
            experiment_id=experiment.id,
            variant_id=baseline_variant.id,
            runner_type=runner_type_str,
        )
        session.add(baseline_run)
        await session.flush()

        try:
            from app.services.trial_execution import TrialExecutionService

            baseline_run.execution_provenance = "REAL_EXECUTION" if runner_type_str == "real_ai" else ("LOCAL_SIMULATION" if runner_type_str == "synthetic" else "LEGACY")
            await TrialExecutionService.execute_trials(
                session, baseline_run, self.runner,
                metrics_to_measure=plan.metrics_to_measure,
                is_candidate=False,
            )

            # ── Step 10b: Candidate run ───────────────────────────────────────
            candidate_run = ExperimentRun(
                experiment_id=experiment.id,
                variant_id=candidate_variant.id,
                runner_type=runner_type_str,
            )
            candidate_run.execution_provenance = "REAL_EXECUTION" if runner_type_str == "real_ai" else ("LOCAL_SIMULATION" if runner_type_str == "synthetic" else "LEGACY")
            session.add(candidate_run)
            await session.flush()

            await TrialExecutionService.execute_trials(
                session, candidate_run, self.runner,
                metrics_to_measure=plan.metrics_to_measure,
                is_candidate=True,
            )
            await session.flush()
        except Exception as e:
            await ExperimentStateMachine.transition(session, experiment, ExperimentState.FAILED)
            experiment.error_message = f"Execution failed: {str(e)}"
            await session.flush()
            return experiment

        # ── Step 11: Evaluate constraints ─────────────────────────────────────
        await ExperimentStateMachine.transition(session, experiment, ExperimentState.MEASURING)

        stmt = select(Constraint).where(Constraint.project_id == project.id)
        constraints = (await session.execute(stmt)).scalars().all()

        stmt_metrics = select(MetricResult).where(MetricResult.run_id == candidate_run.id)
        candidate_metrics = (await session.execute(stmt_metrics)).scalars().all()

        stmt_base_metrics = select(MetricResult).where(MetricResult.run_id == baseline_run.id)
        baseline_metrics = (await session.execute(stmt_base_metrics)).scalars().all()

        evaluations = ConstraintEngine.evaluate(constraints, candidate_metrics)

        # ── Step 12: Decision ─────────────────────────────────────────────────
        decision_result, rationale = DecisionEngine.decide(experiment, candidate_run, evaluations)

        decision = Decision(
            experiment_id=experiment.id,
            result=decision_result.value,
            rationale=rationale,
            constraint_evaluations=[
                {"metric": e.metric_name, "passed": e.passed} for e in evaluations
            ],
        )
        session.add(decision)

        experiment.adopted = (decision_result == DecisionResult.RETAIN)
        experiment.hypothesis_confirmed = (decision_result == DecisionResult.RETAIN)

        # ── Step 13: Researcher analysis & evidence ───────────────────────────
        await ExperimentStateMachine.transition(session, experiment, ExperimentState.ANALYZING)

        base_m_dict = {m.metric_name: m.value for m in baseline_metrics}
        cand_m_dict = {m.metric_name: m.value for m in candidate_metrics}

        experiment.baseline_metrics = {
            **base_m_dict,
            "source": baseline_metrics[0].source if baseline_metrics else None,
        }
        experiment.candidate_metrics = {
            **cand_m_dict,
            "source": candidate_metrics[0].source if candidate_metrics else None,
        }

        conclusion = await self.researcher.analyze_results(
            hypothesis.statement,
            base_m_dict,
            cand_m_dict,
            decision_result == DecisionResult.RETAIN,
        )

        await EvidenceService.create_evidence(
            session, experiment, candidate_run,
            baseline_metrics, candidate_metrics,
            claim=hyp_schema.claim,
            conclusion=conclusion,
        )

        experiment.conclusion = conclusion
        hypothesis.conclusion = conclusion
        hypothesis.status = "tested"

        await ExperimentStateMachine.transition(session, experiment, ExperimentState.COMPLETED)

        await session.commit()
        await session.refresh(experiment)
        return experiment
