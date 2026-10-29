import asyncio
import os
import sys
import json
from datetime import datetime

# Ensure backend root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import async_session_maker
from app.db.models import Project, Constraint, ResearchSession, Experiment, ExperimentVariant, MetricResult, Decision, Evidence, ExperimentRun, ExperimentTrial
from app.gateway.gateway import ModelGateway
from app.services.ai_benchmark import RealAIBenchmarkRunner
from app.services.trial_execution import TrialExecutionService
from app.schemas.evaluation import EvaluationPolicy
from app.services.constraints import ConstraintEngine
from app.services.decision import DecisionEngine
from sqlalchemy import select

async def run_controlled_benchmark():
    async with async_session_maker() as session:
        # 1. Create a Project
        project = Project(
            name="Real Nemotron Controlled Validation",
            objective="Improve accuracy above 90%",
            target_system_description="Sentiment Classifier"
        )
        session.add(project)
        await session.flush()

        # 2. Add Constraints
        c1 = Constraint(project_id=project.id, metric_name="quality_score", operator=">=", required_value=0.9)
        c2 = Constraint(project_id=project.id, metric_name="error_rate", operator="<=", required_value=0.05)
        session.add(c1)
        session.add(c2)
        await session.flush()

        # 3. Create Research Session
        rs = ResearchSession(
            project_id=project.id,
            max_iterations=1,
            max_experiments=1
        )
        session.add(rs)
        await session.flush()

        # 4. Explicit controlled configuration (bypass autonomous agents)
        config = {
            "model": "nvidia/llama-3.1-nemotron-70b-instruct",
            "provider": "nebius",
            "sample_count": 2,  # minimum valid deterministic subset
            "temperature": 0.0
        }

        variant = ExperimentVariant(
            project_id=project.id,
            name="Controlled Validation Variant",
            system_configuration=config,
            is_baseline=False
        )
        session.add(variant)
        await session.flush()

        experiment = Experiment(
            project_id=project.id,
            session_id=rs.id,
            name="Controlled Validation Run",
            experiment_type="controlled",
            candidate_description="Explicit controlled configuration",
            status="running"
        )
        session.add(experiment)
        await session.flush()

        policy_snapshot = {
            "min_trials": 1,
            "max_trials": 1,
            "failure_tolerance_ratio": 0.0
        }

        run = ExperimentRun(
            experiment_id=experiment.id,
            variant_id=variant.id,
            runner_type="real_ai",
            execution_provenance="REAL_EXECUTION",
            evaluation_policy_snapshot=policy_snapshot,
            status="pending"
        )
        session.add(run)
        await session.flush()
        await session.commit() # Commit to DB so TrialExecutionService can pick it up

        print(f"Executing explicit controlled experiment {experiment.id}")

        # 5. Set up gateway and runner
        gateway = ModelGateway()
        runner = RealAIBenchmarkRunner(gateway)
        # Monkeypatch dataset to smallest valid deterministic subset
        runner.dataset = runner.dataset[:2]

        try:
            # 6. Execute explicitly
            aggregated_evidence = await TrialExecutionService.execute_trials(
                session=session,
                run=run,
                runner=runner
            )

            # 7. Evaluate Constraints (Deterministic)
            stmt = select(Constraint).where(Constraint.project_id == project.id)
            constraints = (await session.execute(stmt)).scalars().all()

            evaluations = ConstraintEngine.evaluate(constraints, aggregated_evidence)

            # 8. Decision
            decision_result, rationale = DecisionEngine.decide(experiment, run, evaluations)

            decision = Decision(
                experiment_id=experiment.id,
                result=decision_result.value,
                rationale=rationale,
                constraint_evaluations=[
                    {"metric": e.metric_name, "passed": e.passed} for e in evaluations
                ],
            )
            session.add(decision)

            experiment.status = "completed"
            await session.commit()
            print(f"Controlled Validation Completed. Decision: {decision_result.value}")
            print(f"Rationale: {rationale}")

            # Verify DB Output
            print("\n--- DB Output Verification ---")

            runs_stmt = select(ExperimentRun).where(ExperimentRun.experiment_id == experiment.id)
            runs = (await session.execute(runs_stmt)).scalars().all()
            for r in runs:
                print(f"Run ID: {r.id}, Type: {r.runner_type}, Provenance: {r.execution_provenance}")
                print(f"Policy Snapshot: {r.evaluation_policy_snapshot}")
                print(f"Execution Metadata: {r.execution_metadata}")

                trials_stmt = select(ExperimentTrial).where(ExperimentTrial.run_id == r.id)
                trials = (await session.execute(trials_stmt)).scalars().all()
                for t in trials:
                    print(f"  Trial {t.trial_index}, Status: {t.status}, Provenance: {t.execution_provenance}")

                metrics_stmt = select(MetricResult).where(MetricResult.run_id == r.id)
                metrics = (await session.execute(metrics_stmt)).scalars().all()
                for m in metrics:
                    print(f"  Metric: {m.metric_name} = {m.value}")

        except Exception as e:
            print(f"Controlled Validation Failed (Expected if Nebius is offline): {e}")
            experiment.status = "failed"
            await session.commit()

if __name__ == "__main__":
    asyncio.run(run_controlled_benchmark())
