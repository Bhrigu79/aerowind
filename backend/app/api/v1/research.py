from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db_session
from app.db.models import Experiment, Project, Evidence, Decision, ExperimentPlan, ExperimentRun, MetricResult, ResearchSession, Constraint
from app.gateway.gateway import get_gateway, ModelGateway
from app.services.orchestrator import ResearchOrchestrator
from app.services.session import SessionOrchestrator
from app.services.progress import ObjectiveProgressService
from app.domain.types import classify_runner_provenance
from pydantic import BaseModel

router = APIRouter(prefix="/research", tags=["Research"])

class ResearchSessionCreate(BaseModel):
    max_iterations: int = 5
    max_experiments: int = 10
    budget_usd: float | None = None
    runner_type: str = "synthetic"

@router.post("/sessions/{project_id}")
async def create_research_session(
    project_id: str,
    body: ResearchSessionCreate,
    session: AsyncSession = Depends(get_db_session)
):
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    rs = ResearchSession(
        project_id=project_id,
        max_iterations=body.max_iterations,
        max_experiments=body.max_experiments,
        budget_usd=body.budget_usd
    )
    # Store runner_type in an ad-hoc way or just expect it to be passed during iterate.
    # We will pass it as a query param or body to iterate, or add it to models.
    # For now, let's just add it to models if possible or use a default.
    # Actually, we can add it to ResearchSession model dynamically or just add a query param to `iterate`.
    session.add(rs)
    await session.commit()
    return {"status": "created", "session_id": rs.id}

@router.post("/sessions/{session_id}/iterate")
async def run_session_iteration(
    session_id: str,
    runner_type: str = "synthetic",
    session: AsyncSession = Depends(get_db_session),
    gateway: ModelGateway = Depends(get_gateway)
):
    """
    Execute a research session.

    runner_type must be one of: synthetic | real_ai | nebius
    There is NO silent fallback — an unknown type or unavailable Nebius
    configuration returns an explicit error.  Provenance is never altered.
    """
    runner = None

    if runner_type == "synthetic":
        from app.services.runner import SyntheticExperimentRunner
        runner = SyntheticExperimentRunner()

    elif runner_type == "real_ai":
        from app.services.ai_benchmark import RealAIBenchmarkRunner
        runner = RealAIBenchmarkRunner(gateway)

    elif runner_type == "nebius":
        try:
            from app.services.nebius_runner import NebiusExperimentRunner
            runner = NebiusExperimentRunner()
        except (ValueError, ImportError) as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Nebius runner is unavailable: {exc}. "
                    "Provenance has NOT been downgraded to SIMULATION. "
                    "Configure Nebius credentials to use this runner."
                )
            )
    else:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown runner_type: {runner_type!r}. "
                "Supported values: 'synthetic', 'real_ai', 'nebius'."
            )
        )

    orchestrator = SessionOrchestrator(gateway, runner=runner)
    try:
        await orchestrator.execute_session(session, session_id)
        rs = await session.get(ResearchSession, session_id)
        return {
            "status": rs.status,
            "iteration_count": rs.iteration_count,
            "termination_reason": rs.termination_reason,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, session: AsyncSession = Depends(get_db_session)):
    rs = await session.get(ResearchSession, session_id)
    if not rs:
        raise HTTPException(status_code=404, detail="Session not found")
    return rs

@router.get("/sessions/{session_id}/progress")
async def get_session_progress(session_id: str, session: AsyncSession = Depends(get_db_session)):
    rs = await session.get(ResearchSession, session_id)
    if not rs:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = select(Constraint).where(Constraint.project_id == rs.project_id)
    constraints = (await session.execute(stmt)).scalars().all()

    progress = {"all_passed": False, "metrics_progress": {}}
    if rs.current_best_experiment_id:
        stmt_run = select(ExperimentRun).where(ExperimentRun.experiment_id == rs.current_best_experiment_id)
        runs = (await session.execute(stmt_run)).scalars().all()
        cand_run = next((r for r in runs if "Candidate" in (r.variant.name if hasattr(r.variant, 'name') else "") or not getattr(r.variant, 'is_baseline', True)), None)
        if cand_run:
            stmt_metrics = select(MetricResult).where(MetricResult.run_id == cand_run.id)
            metrics = (await session.execute(stmt_metrics)).scalars().all()
            progress = ObjectiveProgressService.calculate_progress(constraints, [], metrics)

    return progress

@router.get("/experiments/{experiment_id}/plan")
async def get_experiment_plan(experiment_id: str, session: AsyncSession = Depends(get_db_session)):
    stmt = select(ExperimentPlan).where(ExperimentPlan.experiment_id == experiment_id)
    res = await session.execute(stmt)
    plan = res.scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan

@router.get("/experiments/{experiment_id}/evidence")
async def get_experiment_evidence(experiment_id: str, session: AsyncSession = Depends(get_db_session)):
    stmt = select(Evidence).where(Evidence.experiment_id == experiment_id)
    res = await session.execute(stmt)
    evidence = res.scalars().all()
    return evidence

@router.get("/experiments/{experiment_id}/decisions")
async def get_experiment_decisions(experiment_id: str, session: AsyncSession = Depends(get_db_session)):
    stmt = select(Decision).where(Decision.experiment_id == experiment_id)
    res = await session.execute(stmt)
    decisions = res.scalars().all()
    return decisions

@router.get("/experiments/{experiment_id}/certificate")
async def get_experiment_certificate(experiment_id: str, session: AsyncSession = Depends(get_db_session)):
    from app.services.certificate import CertificateService
    try:
        cert = await CertificateService.generate_certificate(session, experiment_id)
        return cert
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/experiments/{experiment_id}/runs")
async def get_experiment_runs(experiment_id: str, session: AsyncSession = Depends(get_db_session)):
    stmt = select(ExperimentRun).where(ExperimentRun.experiment_id == experiment_id)
    res = await session.execute(stmt)
    runs = res.scalars().all()

    run_list = []
    for run in runs:
        stmt_metrics = select(MetricResult).where(MetricResult.run_id == run.id)
        res_metrics = await session.execute(stmt_metrics)
        metrics = res_metrics.scalars().all()
        run_dict = {
            "id": run.id,
            "variant_id": run.variant_id,
            "status": run.status,
            "success": run.success,
            "metrics": [{"name": m.metric_name, "value": m.value, "unit": m.unit} for m in metrics]
        }
        run_list.append(run_dict)
    return run_list

@router.get("/projects/{project_id}/graph")
async def get_research_graph(project_id: str, session: AsyncSession = Depends(get_db_session)):
    from sqlalchemy.orm import selectinload
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    stmt_exp = select(Experiment).options(
        selectinload(Experiment.plan).selectinload(ExperimentPlan.candidate_variant),
        selectinload(Experiment.plan).selectinload(ExperimentPlan.baseline_variant),
        selectinload(Experiment.decisions),
        selectinload(Experiment.runs).selectinload(ExperimentRun.metric_results)
    ).where(Experiment.project_id == project_id).order_by(Experiment.created_at.asc())

    exps = (await session.execute(stmt_exp)).scalars().all()

    nodes = []
    edges = []

    stmt_constraints = select(Constraint).where(Constraint.project_id == project_id)
    project_constraints = (await session.execute(stmt_constraints)).scalars().all()

    nodes.append({
        "id": "root",
        "type": "objective",
        "data": {
            "title": "Objective",
            "objective": project.objective,
            "constraints": [{k: v for k, v in c.__dict__.items() if not k.startswith('_')} for c in project_constraints] if project_constraints else project.constraints
        }
    })

    prev_retained_id = "root"

    for i, exp in enumerate(exps):
        decision_val = exp.decisions[0].result if exp.decisions else "pending"
        if exp.status == "failed" or exp.error_message:
            decision_val = "REJECT"


        # Calculate what changed
        what_changed = {}
        if exp.plan and exp.plan.candidate_variant and exp.plan.baseline_variant:
            c_conf = exp.plan.candidate_variant.system_configuration or {}
            b_conf = exp.plan.baseline_variant.system_configuration or {}
            for k, v in c_conf.items():
                b_v = b_conf.get(k)
                if b_v != v:
                    what_changed[k] = {"from": b_v, "to": v}

        # Check provenance
        provenance = "UNKNOWN / INVALID"
        if exp.runs:
            # We can use the candidate run or any run's type, usually they are the same
            provenance = classify_runner_provenance(exp.runs[0].runner_type)

        node = {
            "id": exp.id,
            "type": "experiment",
            "data": {
                "title": exp.name,
                "state": exp.status,
                "decision": decision_val,
                "created_at": exp.created_at.isoformat(),
                "hypothesis": exp.candidate_description,
                "strategy_reason": exp.strategy_reason,
                "baseline_metrics": exp.baseline_metrics,
                "candidate_metrics": exp.candidate_metrics,
                "error_message": exp.error_message,
                "what_changed": what_changed,
                "runner_type": provenance
            }
        }
        nodes.append(node)

        if prev_retained_id == "root":
            edges.append({"id": f"e_root_{exp.id}", "source": "root", "target": exp.id, "label": "init"})
        else:
            edges.append({"id": f"e_{prev_retained_id}_{exp.id}", "source": prev_retained_id, "target": exp.id, "label": "branch"})

        if decision_val == "RETAIN" or exp.adopted:
            prev_retained_id = exp.id

    summary = {
        "total_experiments": len(exps),
        "retained": sum(1 for e in exps if e.adopted),
        "failed": sum(1 for e in exps if e.status == "failed")
    }

    # Find current best experiment
    current_best = None
    best_config = None
    for exp in reversed(exps):
        if exp.adopted:
            current_best = exp.id
            if exp.plan and exp.plan.candidate_variant:
                best_config = exp.plan.candidate_variant.system_configuration
            break

    # Calculate current gaps using latest session progress
    stmt_sessions = select(ResearchSession).where(ResearchSession.project_id == project_id).order_by(ResearchSession.created_at.desc()).limit(1)
    last_session = (await session.execute(stmt_sessions)).scalars().first()
    gaps = {}
    if last_session and last_session.current_best_experiment_id:
        stmt_run = select(ExperimentRun).where(ExperimentRun.experiment_id == last_session.current_best_experiment_id)
        runs = (await session.execute(stmt_run)).scalars().all()
        cand_run = next((r for r in runs if not getattr(r.variant, 'is_baseline', True)), None)
        if cand_run:
            stmt_metrics = select(MetricResult).where(MetricResult.run_id == cand_run.id)
            metrics = (await session.execute(stmt_metrics)).scalars().all()

            from app.services.progress import ObjectiveProgressService
            stmt_constraints = select(Constraint).where(Constraint.project_id == project_id)
            constraints = (await session.execute(stmt_constraints)).scalars().all()

            progress = ObjectiveProgressService.calculate_progress(constraints, [], metrics)
            gaps = progress.get("metrics_progress", {})

    return {
        "nodes": nodes,
        "edges": edges,
        "current_best": current_best,
        "current_best_config": best_config,
        "current_gaps": gaps,
        "summary": summary,
        "session_id": last_session.id if last_session else None
    }
