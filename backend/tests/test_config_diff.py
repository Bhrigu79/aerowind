import pytest
from app.core.config_validator import ConfigurationValidator
from app.services.strategy import ResearchStrategyService
from app.db.models import ExperimentPlan, ExperimentVariant, Experiment

def test_a_implicit_defaults():
    baseline = {}
    candidate = {
        "retrieval_enabled": True,
        "chain_of_thought": True,
        "prompt_strategy": "structured"
    }
    changed = ConfigurationValidator.diff_effective_config(baseline, candidate)
    assert set(changed) == {"retrieval_enabled", "chain_of_thought", "prompt_strategy"}

def test_b_lying_llm_metadata():
    # Orchestrator uses diff_effective_config regardless of LLM metadata
    baseline = {}
    candidate = {
        "retrieval_enabled": True,
        "chain_of_thought": True,
        "prompt_strategy": "structured"
    }
    changed = ConfigurationValidator.diff_effective_config(baseline, candidate)
    # LLM might say changed_variables = ["prompt_strategy"], but diff computes all 3
    assert set(changed) == {"retrieval_enabled", "chain_of_thought", "prompt_strategy"}

def test_c_false_llm_claim():
    baseline = {"temperature": 0.7, "model": "default"}
    candidate = {"temperature": 0.7, "model": "default"}
    changed = ConfigurationValidator.diff_effective_config(baseline, candidate)
    # LLM might claim temperature and model changed, but diff is empty
    assert len(changed) == 0

def test_d_normalized_strategy_validation():
    baseline = {}
    candidate = {
        "temperature": 0.7,
        "max_tokens": 1024,
        "few_shot_count": 0,
        "retrieval_enabled": False,
        "chain_of_thought": False,
        "model": "default",
        "prompt_strategy": "direct",
        "pipeline_mode": "single"
    }
    # These are effectively identical, so validation for any dimension should be False
    assert ResearchStrategyService.validate_strategy_change(baseline, candidate, "temperature") == False
    assert ResearchStrategyService.validate_strategy_change(baseline, candidate, "retrieval_enabled") == False
    assert len(ConfigurationValidator.diff_effective_config(baseline, candidate)) == 0

def test_e_real_changed_dimension():
    baseline = {}
    candidate = {"prompt_strategy": "structured"}
    changed = ConfigurationValidator.diff_effective_config(baseline, candidate)
    assert changed == ["prompt_strategy"]
