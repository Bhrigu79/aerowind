import json
from typing import List, Dict, Set, Optional, Tuple
from app.db.models import Experiment, ExperimentRun, ExperimentTrial, MetricResult, Decision, Evidence, ComparisonEvaluation
from app.schemas.research import (
    ResearchState, ParetoFrontier, FailureAtlas,
    EvidenceGraph, EvidenceNode, EvidenceEdge, EvidenceNodeType, EvidenceEdgeType
)
from app.core.config_validator import ConfigurationValidator

class EvidenceGraphService:
    @staticmethod
    def _fingerprint(config: dict) -> str:
        normalized = ConfigurationValidator.normalize(config)
        return json.dumps(normalized, sort_keys=True)

    @staticmethod
    def build_graph(
        experiments: List[Experiment],
        comparisons: Optional[List[ComparisonEvaluation]] = None,
        research_state: Optional[ResearchState] = None,
        pareto_frontier: Optional[ParetoFrontier] = None,
        failure_atlas: Optional[FailureAtlas] = None
    ) -> EvidenceGraph:

        nodes: Dict[str, EvidenceNode] = {}
        edges: Set[Tuple[str, str, EvidenceEdgeType, Optional[str]]] = set()

        comparisons = comparisons or []

        def add_node(n_id: str, n_type: EvidenceNodeType, src_id: str, meta: dict = None):
            if n_id not in nodes:
                nodes[n_id] = EvidenceNode(
                    node_id=n_id,
                    node_type=n_type,
                    source_id=src_id,
                    metadata_info=meta or {}
                )

        def add_edge(src: str, tgt: str, rel: EvidenceEdgeType, prov: Optional[str] = None):
            edges.add((src, tgt, rel, prov))

        # We must sort inputs deterministically to ensure deterministic order if edges/nodes are ever iterated
        sorted_experiments = sorted(experiments, key=lambda e: e.id)

        for exp in sorted_experiments:
            exp_node_id = f"exp_{exp.id}"
            add_node(exp_node_id, EvidenceNodeType.EXPERIMENT, exp.id, {"status": exp.status})

            # Extract configuration if plan exists
            if exp.plan and exp.plan.candidate_variant:
                raw_config = exp.plan.candidate_variant.system_configuration
                fp = EvidenceGraphService._fingerprint(raw_config)
                config_node_id = f"config_{fp}"
                add_node(config_node_id, EvidenceNodeType.CONFIGURATION, fp, {"canonical_fingerprint": fp})

                # EXPERIMENT -> TESTED -> CONFIGURATION
                add_edge(exp_node_id, config_node_id, EvidenceEdgeType.TESTED, exp.id)

            # Decisions
            for dec in sorted(exp.decisions, key=lambda d: d.id):
                dec_node_id = f"dec_{dec.id}"
                add_node(dec_node_id, EvidenceNodeType.DECISION, dec.id, {"result": dec.result})
                add_edge(exp_node_id, dec_node_id, EvidenceEdgeType.RESULTED_IN, dec.id)

            # Evidence Certificates
            for ev in sorted(exp.evidence, key=lambda e: e.id):
                ev_node_id = f"ev_{ev.id}"
                add_node(ev_node_id, EvidenceNodeType.EVIDENCE_CERTIFICATE, ev.id, {"claim": ev.claim})
                # OMITTED EDGE: Evidence mapping to Decision.
                # Evidence in the database only points to Experiment. It does not contain a decision_id.
                # To satisfy the provenance rule (no inferred relationships), we omit the PRODUCED edge here.

            # Runs
            for run in sorted(exp.runs, key=lambda r: r.id):
                run_node_id = f"run_{run.id}"
                add_node(run_node_id, EvidenceNodeType.EXPERIMENT_RUN, run.id, {"tier": run.evaluation_tier, "success": run.success})
                add_edge(exp_node_id, run_node_id, EvidenceEdgeType.HAS_RUN, run.id)

                # Trials
                for trial in sorted(run.trials, key=lambda t: t.id):
                    trial_node_id = f"trial_{trial.id}"
                    add_node(trial_node_id, EvidenceNodeType.TRIAL, trial.id, {"status": trial.status, "index": trial.trial_index})
                    add_edge(run_node_id, trial_node_id, EvidenceEdgeType.HAS_TRIAL, trial.id)

                    # Metrics tied to this trial
                    for metric in sorted(trial.metric_results, key=lambda m: m.id):
                        met_node_id = f"metric_{metric.id}"
                        add_node(met_node_id, EvidenceNodeType.METRIC_RESULT, metric.id, {"name": metric.metric_name, "value": metric.value})
                        add_edge(trial_node_id, met_node_id, EvidenceEdgeType.PRODUCED_METRIC, metric.id)

                # Metrics tied directly to run (legacy/aggregate)
                for metric in sorted(run.metric_results, key=lambda m: m.id):
                    if not metric.trial_id:
                        met_node_id = f"metric_{metric.id}"
                        add_node(met_node_id, EvidenceNodeType.METRIC_RESULT, metric.id, {"name": metric.metric_name, "value": metric.value})
                        add_edge(run_node_id, met_node_id, EvidenceEdgeType.PRODUCED_METRIC, metric.id)

        # Comparisons
        for comp in sorted(comparisons, key=lambda c: c.id):
            comp_node_id = f"comp_{comp.id}"
            add_node(comp_node_id, EvidenceNodeType.COMPARISON_EVALUATION, comp.id, {"dataset_version": comp.dataset_version})
            add_edge(f"run_{comp.candidate_run_id}", comp_node_id, EvidenceEdgeType.PRODUCED_EVALUATION, comp.id)

        # Failure Atlas
        if failure_atlas:
            for entry in sorted(failure_atlas.entries, key=lambda e: e.fingerprint):
                fail_node_id = f"fail_{entry.fingerprint}"
                add_node(fail_node_id, EvidenceNodeType.FAILURE_ATLAS_ENTRY, entry.fingerprint, {"failure_type": entry.failure_type})

                config_node_id = f"config_{entry.fingerprint}"
                if config_node_id in nodes:
                    add_edge(config_node_id, fail_node_id, EvidenceEdgeType.HAS_FAILURE_EVIDENCE, entry.fingerprint)

        # Pareto Frontier
        if pareto_frontier:
            pf_node_id = "pareto_frontier_current"
            add_node(pf_node_id, EvidenceNodeType.PARETO_FRONTIER, "pareto_frontier_current", {"objective_metrics": pareto_frontier.objective_metrics})

            for fp in sorted(pareto_frontier.frontier_fingerprints):
                config_node_id = f"config_{fp}"
                if config_node_id in nodes:
                    add_edge(config_node_id, pf_node_id, EvidenceEdgeType.MEMBER_OF, fp)

        # Research State (as the current aggregate)
        if research_state:
            rs_node_id = "research_state_current"
            add_node(rs_node_id, EvidenceNodeType.RESEARCH_STATE, "research_state_current", {"objective_id": research_state.objective_id})

            # Edge from research state to explored configurations
            for explored in sorted(research_state.explored_configurations, key=lambda x: x.fingerprint):
                config_node_id = f"config_{explored.fingerprint}"
                if config_node_id in nodes:
                    add_edge(rs_node_id, config_node_id, EvidenceEdgeType.DERIVED_FROM, explored.fingerprint)

        # Construct final lists, sort edges to ensure determinism
        final_nodes = [nodes[k] for k in sorted(nodes.keys())]
        final_edges = []
        for src, tgt, rel, prov in sorted(list(edges), key=lambda x: (x[0], x[1], x[2].value)):
            # Only add edge if both nodes actually exist (failsafe)
            if src in nodes and tgt in nodes:
                final_edges.append(EvidenceEdge(
                    source_node_id=src,
                    target_node_id=tgt,
                    relation_type=rel,
                    provenance=prov
                ))

        return EvidenceGraph(nodes=final_nodes, edges=final_edges)
