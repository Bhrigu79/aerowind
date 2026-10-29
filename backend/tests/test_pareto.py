import pytest
import copy
import math
from app.schemas.research import ResearchState, ExploredConfiguration, ObservedEffect
from app.schemas.evaluation import EvaluationPolicy
from app.domain.types import MetricDirection
from app.services.pareto import ParetoFrontierService

def make_dummy_state() -> ResearchState:
    return ResearchState(
        objective_id="obj_1",
        objective_constraints={},
        optimization_directions={},
        policy_snapshot=EvaluationPolicy()
    )

def add_config(state: ResearchState, fp: str, run_id: str, is_feasible: bool, metrics: dict):
    state.explored_configurations.append(ExploredConfiguration(
        canonical_configuration={"test": fp},
        fingerprint=fp,
        experiment_id=f"exp_{run_id}",
        run_id=run_id,
        decision="RETAIN" if is_feasible else "REJECT",
        changed_dimensions=["test"],
        dataset_version="v1",
        execution_provenance="pytest"
    ))
    if is_feasible:
        state.feasible_configurations.append(fp)

    for m, v in metrics.items():
        state.observed_effects.append(ObservedEffect(
            metric=m,
            direction=MetricDirection.HIGHER_IS_BETTER,
            baseline_value=0.0,
            candidate_value=v,
            improvement_delta=0.0,
            effect_above_mpe=True,
            statistically_supported=True,
            confidence_interval_lower=0.0,
            confidence_interval_upper=0.0,
            sample_size=10,
            source_experiment_id=f"exp_{run_id}",
            source_run_id=run_id
        ))

def test_A_single_feasible():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"quality": 90, "cost": 10})
    frontier = ParetoFrontierService.build_frontier(state, ["quality", "cost"], {"quality": MetricDirection.HIGHER_IS_BETTER, "cost": MetricDirection.LOWER_IS_BETTER})
    assert "A" in frontier.frontier_fingerprints

def test_B_dominated_excluded():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"quality": 95, "cost": 10})
    add_config(state, "B", "run_B", True, {"quality": 90, "cost": 15})

    frontier = ParetoFrontierService.build_frontier(state, ["quality", "cost"], {"quality": MetricDirection.HIGHER_IS_BETTER, "cost": MetricDirection.LOWER_IS_BETTER})
    assert "A" in frontier.frontier_fingerprints
    assert "B" not in frontier.frontier_fingerprints
    assert "B" in frontier.dominated_fingerprints
    assert "B" in frontier.dominance_relationships["A"]

def test_C_R_tradeoff_configurations():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"quality": 95, "cost": 20})
    add_config(state, "B", "run_B", True, {"quality": 90, "cost": 15})

    frontier = ParetoFrontierService.build_frontier(state, ["quality", "cost"], {"quality": MetricDirection.HIGHER_IS_BETTER, "cost": MetricDirection.LOWER_IS_BETTER})
    assert set(frontier.frontier_fingerprints) == {"A", "B"}

def test_D_E_directions_handled_correctly():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"quality": 95, "cost": 20})
    add_config(state, "B", "run_B", True, {"quality": 90, "cost": 15})

    frontier = ParetoFrontierService.build_frontier(state, ["quality", "cost"], {"quality": MetricDirection.HIGHER_IS_BETTER, "cost": MetricDirection.HIGHER_IS_BETTER})
    assert frontier.frontier_fingerprints == ["A"]
    assert "B" in frontier.dominated_fingerprints

def test_F_equality_does_not_dominate():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"q": 90})
    add_config(state, "B", "run_B", True, {"q": 90})

    frontier = ParetoFrontierService.build_frontier(state, ["q"], {"q": MetricDirection.HIGHER_IS_BETTER})
    assert set(frontier.frontier_fingerprints) == {"A", "B"}

def test_H_I_K_L_Q_infeasible_excluded():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"q": 90})
    add_config(state, "B", "run_B", False, {"q": 99})

    frontier = ParetoFrontierService.build_frontier(state, ["q"], {"q": MetricDirection.HIGHER_IS_BETTER})
    assert frontier.frontier_fingerprints == ["A"]
    assert "B" not in frontier.frontier_fingerprints
    assert "B" not in frontier.dominated_fingerprints

def test_J_missing_metric_excluded():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"quality": 90})
    add_config(state, "B", "run_B", True, {"quality": 90, "cost": 10})

    frontier = ParetoFrontierService.build_frontier(state, ["quality", "cost"], {"quality": MetricDirection.HIGHER_IS_BETTER, "cost": MetricDirection.LOWER_IS_BETTER})
    assert frontier.frontier_fingerprints == ["B"]
    assert "A" not in frontier.frontier_fingerprints
    assert "A" not in frontier.dominated_fingerprints

def test_M_three_way_dominance():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"q": 95})
    add_config(state, "B", "run_B", True, {"q": 90})
    add_config(state, "C", "run_C", True, {"q": 85})

    frontier = ParetoFrontierService.build_frontier(state, ["q"], {"q": MetricDirection.HIGHER_IS_BETTER})
    assert frontier.frontier_fingerprints == ["A"]
    assert set(frontier.dominated_fingerprints) == {"B", "C"}
    assert "B" in frontier.dominance_relationships["A"]
    assert "C" in frontier.dominance_relationships["A"]
    assert "C" in frontier.dominance_relationships["B"]

def test_N_O_no_global_winner_or_weighted_scoring():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"q": 1000000, "c": 20})
    add_config(state, "B", "run_B", True, {"q": 1, "c": 1})
    frontier = ParetoFrontierService.build_frontier(state, ["q", "c"], {"q": MetricDirection.HIGHER_IS_BETTER, "c": MetricDirection.LOWER_IS_BETTER})
    assert set(frontier.frontier_fingerprints) == {"A", "B"}
    assert not hasattr(frontier, "overall_score")
    assert not hasattr(frontier, "winner")

def test_P_T_deterministic_and_no_mutation():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"q": 95, "c": 20})
    add_config(state, "B", "run_B", True, {"q": 90, "c": 15})

    state_copy = copy.deepcopy(state)

    f1 = ParetoFrontierService.build_frontier(state, ["q", "c"], {"q": MetricDirection.HIGHER_IS_BETTER, "c": MetricDirection.LOWER_IS_BETTER})
    f2 = ParetoFrontierService.build_frontier(state, ["c", "q"], {"q": MetricDirection.HIGHER_IS_BETTER, "c": MetricDirection.LOWER_IS_BETTER})

    assert f1.frontier_fingerprints == f2.frontier_fingerprints
    assert f1.dominated_fingerprints == f2.dominated_fingerprints
    assert f1.objective_metrics == f2.objective_metrics

    assert len(state.explored_configurations) == len(state_copy.explored_configurations)
    assert len(state.observed_effects) == len(state_copy.observed_effects)

def test_S_cross_run_contamination():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"q": 95})
    add_config(state, "B", "run_B", True, {"q": 99})

    frontier = ParetoFrontierService.build_frontier(state, ["q"], {"q": MetricDirection.HIGHER_IS_BETTER})
    assert frontier.frontier_fingerprints == ["B"]
    assert frontier.metric_values["A"]["q"] == 95
    assert frontier.metric_values["B"]["q"] == 99

def test_duplicate_metric_aggregation():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"q": 90.0})
    # Add identical duplicate metric for run_A (should be accepted)
    state.observed_effects.append(ObservedEffect(
        metric="q",
        direction=MetricDirection.HIGHER_IS_BETTER,
        baseline_value=0.0,
        candidate_value=90.0,
        improvement_delta=0.0,
        effect_above_mpe=True,
        statistically_supported=True,
        confidence_interval_lower=0.0,
        confidence_interval_upper=0.0,
        sample_size=10,
        source_experiment_id="exp_run_A",
        source_run_id="run_A"
    ))

    # B has conflicting duplicates, should be excluded completely
    add_config(state, "B", "run_B", True, {"q": 95.0})
    state.observed_effects.append(ObservedEffect(
        metric="q",
        direction=MetricDirection.HIGHER_IS_BETTER,
        baseline_value=0.0,
        candidate_value=100.0,
        improvement_delta=0.0,
        effect_above_mpe=True,
        statistically_supported=True,
        confidence_interval_lower=0.0,
        confidence_interval_upper=0.0,
        sample_size=10,
        source_experiment_id="exp_run_B",
        source_run_id="run_B"
    ))

    frontier = ParetoFrontierService.build_frontier(state, ["q"], {"q": MetricDirection.HIGHER_IS_BETTER})
    assert frontier.metric_values["A"]["q"] == 90.0
    assert set(frontier.frontier_fingerprints) == {"A"} # B excluded due to corrupt/conflicting data

def test_nan_infinity_exclusion():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"q": math.nan})
    add_config(state, "B", "run_B", True, {"q": math.inf})
    add_config(state, "C", "run_C", True, {"q": -math.inf})
    add_config(state, "D", "run_D", True, {"q": 90})

    frontier = ParetoFrontierService.build_frontier(state, ["q"], {"q": MetricDirection.HIGHER_IS_BETTER})
    assert frontier.frontier_fingerprints == ["D"]
    assert "A" not in frontier.dominated_fingerprints
    assert "B" not in frontier.dominated_fingerprints
    assert "C" not in frontier.dominated_fingerprints
    assert "A" not in frontier.frontier_fingerprints

def test_duplicate_effective_configuration():
    state1 = make_dummy_state()
    # Adding same fingerprint A twice, once with run_1, once with run_2
    add_config(state1, "A", "run_2", True, {"q": 90})
    add_config(state1, "A", "run_1", True, {"q": 95})

    state2 = make_dummy_state()
    # Different order
    add_config(state2, "A", "run_1", True, {"q": 95})
    add_config(state2, "A", "run_2", True, {"q": 90})

    f1 = ParetoFrontierService.build_frontier(state1, ["q"], {"q": MetricDirection.HIGHER_IS_BETTER})
    f2 = ParetoFrontierService.build_frontier(state2, ["q"], {"q": MetricDirection.HIGHER_IS_BETTER})

    # Run ID lexicographically smaller should win, so run_1 wins. run_1 has q=95.
    assert f1.metric_values["A"]["q"] == 95
    assert f2.metric_values["A"]["q"] == 95
    assert f1.source_run_ids["A"] == "run_1"
    assert f2.source_run_ids["A"] == "run_1"

def test_current_best_semantics():
    state = make_dummy_state()
    add_config(state, "A", "run_A", True, {"q": 90})
    add_config(state, "B", "run_B", True, {"q": 100})
    state.current_best_fingerprint = "A"

    frontier = ParetoFrontierService.build_frontier(state, ["q"], {"q": MetricDirection.HIGHER_IS_BETTER})

    assert frontier.current_best_fingerprint == "A"
    assert frontier.current_best_is_dominated is True
    assert state.current_best_fingerprint == "A" # state is not mutated

def test_adversarial_feasibility():
    state = make_dummy_state()
    # D is explicitly feasible but we'll mock that its constraints were manually overridden
    add_config(state, "D", "run_D", True, {"q": 1000})

    # E is infeasible but we manually insert it into feasible_configurations
    add_config(state, "E", "run_E", False, {"q": 2000})
    state.feasible_configurations.append("E")

    frontier = ParetoFrontierService.build_frontier(state, ["q"], {"q": MetricDirection.HIGHER_IS_BETTER})

    # Pareto trusts ResearchState.feasible_configurations, so E enters the frontier
    # This documents the invariant: ResearchState is the trusted source of truth.
    assert "E" in frontier.frontier_fingerprints
    assert "D" in frontier.dominated_fingerprints
