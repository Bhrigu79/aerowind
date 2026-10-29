import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.db.models import Experiment, ComparisonEvaluation
from app.schemas.research import (
    ResearchState, ResearchReplay, ReplayIntegrityStatus, ReplayEvent, ReplayLimitation,
    CritiqueStatus
)
from app.schemas.evaluation import EvaluationPolicy
from app.services.critique import SelfAdversarialCritiqueEngine
from app.services.research_state import ResearchStateService
from app.core.config_validator import ConfigurationValidator
from app.domain.types import EvaluationTier

class ResearchReplayService:
    @staticmethod
    def _hash_id(*parts) -> str:
        m = hashlib.md5()
        for p in parts:
            m.update(str(p).encode('utf-8'))
        return m.hexdigest()

    @staticmethod
    def build_replay(
        session_id: str,
        experiments: List[Experiment],
        evaluations: List[ComparisonEvaluation],
        recorded_research_state: Optional[ResearchState],
        policy_snapshot: EvaluationPolicy,
        objective_snapshot: Dict[str, Any]
    ) -> ResearchReplay:

        limitations = []
        integrity = ReplayIntegrityStatus.VERIFIED

        if not experiments and not recorded_research_state:
            return ResearchReplay(
                replay_id=ResearchReplayService._hash_id("empty", session_id),
                session_id=session_id,
                status=ReplayIntegrityStatus.INSUFFICIENT_HISTORY,
                objective_snapshot=objective_snapshot,
                policy_snapshot=policy_snapshot,
                research_state_snapshot=recorded_research_state or ResearchStateService.build_state(
                    objective_id=objective_snapshot.get("id", "unk"),
                    objective_constraints=objective_snapshot.get("constraints", {}),
                    optimization_directions=objective_snapshot.get("directions", {}),
                    policy_snapshot=policy_snapshot,
                    experiments=[]
                )
            )

        events: List[ReplayEvent] = []
        base_time = datetime(2025, 1, 1)
        replay_hash_parts = [session_id]
        reconstructed_exps = []

        for exp in sorted(experiments, key=lambda x: x.id):
            replay_hash_parts.append(exp.id)
            exp_time = exp.created_at or base_time

            events.append(ReplayEvent(
                event_id=ResearchReplayService._hash_id("exp", exp.id),
                timestamp=exp_time,
                event_type="EXPERIMENT_CREATED",
                description=f"Experiment {exp.name} created.",
                source_artifacts=[exp.id]
            ))

            runs_repr = []
            for run in sorted(exp.runs, key=lambda r: r.id):
                run_time = run.started_at or exp_time
                events.append(ReplayEvent(
                    event_id=ResearchReplayService._hash_id("run", run.id),
                    timestamp=run_time,
                    event_type="RUN_STARTED",
                    description=f"Run started on tier {run.evaluation_tier}.",
                    source_artifacts=[run.id]
                ))

                trials_repr = []
                for trial in sorted(run.trials, key=lambda t: t.id):
                    trial_time = trial.completed_at or run_time
                    events.append(ReplayEvent(
                        event_id=ResearchReplayService._hash_id("trial", trial.id),
                        timestamp=trial_time,
                        event_type="TRIAL_COMPLETED",
                        description=f"Trial {trial.trial_index} completed.",
                        source_artifacts=[trial.id]
                    ))

                    trial_metrics = [m for m in run.metric_results if m.trial_id == trial.id]
                    metrics_repr = []
                    for m in sorted(trial_metrics, key=lambda x: x.id):
                        events.append(ReplayEvent(
                            event_id=ResearchReplayService._hash_id("metric", m.id),
                            timestamp=m.timestamp or trial_time,
                            event_type="METRIC_RECORDED",
                            description=f"Metric {m.metric_name} recorded.",
                            source_artifacts=[m.id]
                        ))
                        metrics_repr.append({
                            "metric_id": m.id,
                            "metric_name": m.metric_name,
                            "value": m.value,
                            "is_legacy": False
                        })

                    trials_repr.append({
                        "trial_id": trial.id,
                        "status": trial.status,
                        "metrics": metrics_repr
                    })

                legacy_metrics = [m for m in run.metric_results if not m.trial_id]
                if legacy_metrics:
                    limitations.append(ReplayLimitation(
                        limitation_type="LEGACY_METRICS",
                        description="Some metrics lack trial provenance.",
                        affected_artifacts=[m.id for m in legacy_metrics]
                    ))
                    integrity = ReplayIntegrityStatus.PARTIALLY_VERIFIED

                runs_repr.append({
                    "run_id": run.id,
                    "tier": run.evaluation_tier,
                    "trials": trials_repr,
                    "legacy_metrics": [{"metric_id": m.id, "value": m.value} for m in legacy_metrics]
                })

            for dec in sorted(exp.decisions, key=lambda d: d.id):
                events.append(ReplayEvent(
                    event_id=ResearchReplayService._hash_id("dec", dec.id),
                    timestamp=dec.created_at or base_time,
                    event_type="DECISION_RECORDED",
                    description=f"Decision {dec.result} recorded.",
                    source_artifacts=[dec.id]
                ))

            for ev in sorted(exp.evidence, key=lambda e: e.id):
                events.append(ReplayEvent(
                    event_id=ResearchReplayService._hash_id("ev", ev.id),
                    timestamp=ev.created_at or base_time,
                    event_type="EVIDENCE_CERTIFIED",
                    description=f"Evidence certified: {ev.claim}",
                    source_artifacts=[ev.id]
                ))

            raw_config = exp.plan.candidate_variant.system_configuration if (hasattr(exp, 'plan') and exp.plan and exp.plan.candidate_variant) else {}
            norm_config = ConfigurationValidator.normalize(raw_config)
            import json
            fp = json.dumps(norm_config, sort_keys=True)

            reconstructed_exps.append({
                "experiment_id": exp.id,
                "configuration_fingerprint": fp,
                "normalized_configuration": norm_config,
                "runs": runs_repr
            })

        for eval in sorted(evaluations, key=lambda e: e.id):
            events.append(ReplayEvent(
                event_id=ResearchReplayService._hash_id("eval", eval.id),
                timestamp=eval.created_at or base_time,
                event_type="EVALUATION_CREATED",
                description=f"Comparison Evaluation between {eval.candidate_run_id} and {eval.baseline_run_id}",
                source_artifacts=[eval.id]
            ))

        reconstructed_state = ResearchStateService.build_state(
            objective_id=objective_snapshot.get("id", "unk"),
            objective_constraints=objective_snapshot.get("constraints", {}),
            optimization_directions=objective_snapshot.get("directions", {}),
            policy_snapshot=policy_snapshot,
            experiments=experiments
        )

        if recorded_research_state:
            rec_fps = sorted([c.fingerprint for c in recorded_research_state.explored_configurations])
            recon_fps = sorted([c.fingerprint for c in reconstructed_state.explored_configurations])

            if rec_fps != recon_fps:
                integrity = ReplayIntegrityStatus.INTEGRITY_MISMATCH
                limitations.append(ReplayLimitation(
                    limitation_type="STATE_MISMATCH",
                    description="Reconstructed state configurations differ from historical record.",
                    affected_artifacts=[]
                ))
                reconstructed_state = recorded_research_state
            else:
                mismatch_decisions = False
                for rec_conf in recorded_research_state.explored_configurations:
                    recon_conf = next((c for c in reconstructed_state.explored_configurations if c.fingerprint == rec_conf.fingerprint), None)
                    if recon_conf and rec_conf.decision != recon_conf.decision:
                        mismatch_decisions = True
                        break

                if mismatch_decisions:
                    integrity = ReplayIntegrityStatus.INTEGRITY_MISMATCH
                    limitations.append(ReplayLimitation(
                        limitation_type="DECISION_MISMATCH",
                        description="Reconstructed decisions differ from historical record. Using historical.",
                        affected_artifacts=[]
                    ))
                    reconstructed_state = recorded_research_state

        critiques = SelfAdversarialCritiqueEngine.evaluate(
            research_state=reconstructed_state,
            experiments=experiments
        )
        for c in critiques:
            c.claim = "[REPLAY_DERIVED] " + c.claim

        # Ensure events are sorted purely deterministically based on timestamp and fallback on id
        events.sort(key=lambda e: (e.timestamp.timestamp() if isinstance(e.timestamp, datetime) else 0.0, e.event_id))

        replay_id = ResearchReplayService._hash_id(*replay_hash_parts)

        return ResearchReplay(
            replay_id=replay_id,
            session_id=session_id,
            status=integrity,
            objective_snapshot=objective_snapshot,
            policy_snapshot=policy_snapshot,
            timeline=events,
            experiments=reconstructed_exps,
            evaluations=[{"id": e.id, "candidate_run": e.candidate_run_id} for e in evaluations],
            research_state_snapshot=reconstructed_state,
            critiques=critiques,
            limitations=limitations
        )
