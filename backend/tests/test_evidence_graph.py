import pytest
import copy
from app.db.models import Experiment, ExperimentRun, ExperimentTrial, MetricResult, Decision, Evidence, ExperimentPlan, ExperimentVariant
from app.schemas.research import (
    ResearchState, ParetoFrontier, FailureAtlas, FailureAtlasEntry,
    EvidenceNodeType, EvidenceEdgeType
)
from app.services.evidence_graph import EvidenceGraphService
from app.domain.types import DecisionResult, EvaluationTier

def create_dummy_experiment(exp_id: str, config_val: str, runs=True):
    exp = Experiment(id=exp_id, status="completed")

    variant = ExperimentVariant(id=f"var_{exp_id}", system_configuration={"val": config_val})
    plan = ExperimentPlan(id=f"plan_{exp_id}", candidate_variant=variant, hypothesis_summary="test", workload="test")
    exp.plan = plan

    if runs:
        run = ExperimentRun(id=f"run_{exp_id}", experiment_id=exp_id, evaluation_tier=EvaluationTier.OPTIMIZATION.value, success=True)
        trial = ExperimentTrial(id=f"trial_{exp_id}", run_id=run.id, trial_index=1, status="completed")
        metric = MetricResult(id=f"metric_{exp_id}", run_id=run.id, trial_id=trial.id, metric_name="q", value=100.0, unit="ms", direction="HIGHER_IS_BETTER", sample_size=10, source="sys")

        trial.metric_results = [metric]
        run.trials = [trial]
        run.metric_results = []
        exp.runs = [run]

    return exp

def test_C_D_E_F_G_lineage():
    exp = create_dummy_experiment("exp_1", "v1")
    dec = Decision(id="dec_1", experiment_id="exp_1", result=DecisionResult.RETAIN.value, rationale="ok")
    exp.decisions = [dec]

    graph = EvidenceGraphService.build_graph(experiments=[exp])

    nodes = {n.node_id: n for n in graph.nodes}
    edges = {(e.source_node_id, e.target_node_id): e.relation_type for e in graph.edges}

    assert "exp_exp_1" in nodes
    assert nodes["exp_exp_1"].node_type == EvidenceNodeType.EXPERIMENT

    fp = EvidenceGraphService._fingerprint({"val": "v1"})
    config_id = f"config_{fp}"
    assert config_id in nodes

    assert edges[("exp_exp_1", config_id)] == EvidenceEdgeType.TESTED
    assert edges[("exp_exp_1", "run_run_exp_1")] == EvidenceEdgeType.HAS_RUN
    assert edges[("run_run_exp_1", "trial_trial_exp_1")] == EvidenceEdgeType.HAS_TRIAL
    assert edges[("trial_trial_exp_1", "metric_metric_exp_1")] == EvidenceEdgeType.PRODUCED_METRIC
    assert edges[("exp_exp_1", "dec_dec_1")] == EvidenceEdgeType.RESULTED_IN

def test_H_P_semantics_preserved():
    exp = create_dummy_experiment("exp_1", "v1")
    dec = Decision(id="dec_1", experiment_id="exp_1", result=DecisionResult.INCONCLUSIVE.value, rationale="timeout")
    exp.decisions = [dec]
    exp.runs[0].success = False # Execution failure

    graph = EvidenceGraphService.build_graph([exp])
    dec_node = next(n for n in graph.nodes if n.node_id == "dec_dec_1")
    assert dec_node.metadata_info["result"] == DecisionResult.INCONCLUSIVE.value

    run_node = next(n for n in graph.nodes if n.node_id == "run_run_exp_1")
    assert run_node.metadata_info["success"] is False

def test_I_J_K_deduplication():
    exp1 = create_dummy_experiment("exp_1", "v1", runs=False)
    exp2 = create_dummy_experiment("exp_2", "v1", runs=False)

    graph = EvidenceGraphService.build_graph([exp1, exp2])

    fp = EvidenceGraphService._fingerprint({"val": "v1"})
    config_id = f"config_{fp}"

    # Should only be one configuration node despite two experiments
    config_nodes = [n for n in graph.nodes if n.node_type == EvidenceNodeType.CONFIGURATION]
    assert len(config_nodes) == 1

    edges = [(e.source_node_id, e.target_node_id) for e in graph.edges if e.target_node_id == config_id]
    assert len(edges) == 2
    assert ("exp_exp_1", config_id) in edges
    assert ("exp_exp_2", config_id) in edges

def test_L_M_W_X_determinism():
    exp1 = create_dummy_experiment("exp_1", "v1")
    exp2 = create_dummy_experiment("exp_2", "v2")

    g1 = EvidenceGraphService.build_graph([exp1, exp2])
    g2 = EvidenceGraphService.build_graph([exp2, exp1])

    assert [n.node_id for n in g1.nodes] == [n.node_id for n in g2.nodes]
    assert [(e.source_node_id, e.target_node_id) for e in g1.edges] == [(e.source_node_id, e.target_node_id) for e in g2.edges]

def test_N_O_missing_dangling():
    # Verify Decision -> Evidence edge is explicitly omitted because Evidence lacks decision_id
    exp = create_dummy_experiment("exp_1", "v1", runs=False)
    ev = Evidence(id="ev_1", claim="test", conclusion="ok")
    dec = Decision(id="dec_1", experiment_id="exp_1", result=DecisionResult.RETAIN.value, rationale="ok")
    exp.evidence = [ev]
    exp.decisions = [dec]

    graph = EvidenceGraphService.build_graph([exp])

    assert any(n.node_id == "ev_ev_1" for n in graph.nodes)
    assert not any(e.relation_type == EvidenceEdgeType.PRODUCED for e in graph.edges)

def test_Q_evaluation_tiers():
    exp = create_dummy_experiment("exp_1", "v1")
    exp.runs[0].evaluation_tier = EvaluationTier.HOLDOUT.value

    graph = EvidenceGraphService.build_graph([exp])
    run_node = next(n for n in graph.nodes if n.node_id == "run_run_exp_1")
    assert run_node.metadata_info["tier"] == EvaluationTier.HOLDOUT.value

def test_R_S_integration():
    exp = create_dummy_experiment("exp_1", "v1", runs=False)
    fp = EvidenceGraphService._fingerprint({"val": "v1"})

    pf = ParetoFrontier(frontier_fingerprints=[fp])
    # mocking policy snapshot for atlas
    from app.schemas.evaluation import EvaluationPolicy
    fa = FailureAtlas(entries=[FailureAtlasEntry(
        canonical_configuration={"val": "v1"},
        fingerprint=fp,
        experiment_id="exp_1",
        run_id="run_1",
        failure_type="CONSTRAINT_FAILURE",
        reason="failed",
        policy_snapshot=EvaluationPolicy()
    )])

    graph = EvidenceGraphService.build_graph([exp], pareto_frontier=pf, failure_atlas=fa)

    pf_node = next((n for n in graph.nodes if n.node_id == "pareto_frontier_current"), None)
    assert pf_node is not None

    config_id = f"config_{fp}"
    assert any(e.source_node_id == config_id and e.target_node_id == "pareto_frontier_current" and e.relation_type == EvidenceEdgeType.MEMBER_OF for e in graph.edges)

    fail_node = f"fail_{fp}"
    assert any(n.node_id == fail_node for n in graph.nodes)
    assert any(e.source_node_id == config_id and e.target_node_id == fail_node and e.relation_type == EvidenceEdgeType.HAS_FAILURE_EVIDENCE for e in graph.edges)

def test_V_immutability():
    exp = create_dummy_experiment("exp_1", "v1")
    exp_copy = copy.deepcopy(exp)

    EvidenceGraphService.build_graph([exp])

    assert exp.id == exp_copy.id
    assert exp.runs[0].id == exp_copy.runs[0].id
