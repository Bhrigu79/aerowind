import pytest
from app.services.strategy import ResearchStrategyService

def test_strategy_validation_dimension_changed():
    baseline = {"temperature": 0.7, "max_tokens": 500}
    candidate = {"temperature": 0.2, "max_tokens": 500}
    assert ResearchStrategyService.validate_strategy_change(baseline, candidate, "temperature") == True

def test_strategy_validation_dimension_unchanged_unrelated_changed():
    baseline = {"temperature": 0.7, "max_tokens": 500}
    candidate = {"temperature": 0.7, "max_tokens": 1000}
    assert ResearchStrategyService.validate_strategy_change(baseline, candidate, "temperature") == False

def test_strategy_validation_dimension_unchanged_nothing_changed():
    baseline = {"temperature": 0.7, "max_tokens": 500}
    candidate = {"temperature": 0.7, "max_tokens": 500}
    assert ResearchStrategyService.validate_strategy_change(baseline, candidate, "temperature") == False

def test_strategy_validation_multiple_dimensions_changed():
    baseline = {"temperature": 0.7, "max_tokens": 500}
    candidate = {"temperature": 0.3, "max_tokens": 1000}
    assert ResearchStrategyService.validate_strategy_change(baseline, candidate, "temperature") == True

def test_strategy_validation_missing_from_baseline():
    baseline = {"max_tokens": 500}
    candidate = {"temperature": 0.2, "max_tokens": 500}
    # If missing from baseline, but added in candidate, it's a material change
    assert ResearchStrategyService.validate_strategy_change(baseline, candidate, "temperature") == True

def test_strategy_validation_missing_from_candidate():
    baseline = {"temperature": 0.7, "max_tokens": 500}
    candidate = {"max_tokens": 500}
    # If missing from candidate but present in baseline with default value, it's NOT a change
    assert ResearchStrategyService.validate_strategy_change(baseline, candidate, "temperature") == False

def test_strategy_validation_missing_from_both():
    baseline = {"max_tokens": 500}
    candidate = {"max_tokens": 500}
    # If missing from both, the candidate didn't actually target this dimension
    assert ResearchStrategyService.validate_strategy_change(baseline, candidate, "temperature") == False

def test_strategy_validation_same_config():
    baseline = {"temperature": 0.7}
    candidate = {"temperature": 0.7}
    assert ResearchStrategyService.validate_strategy_change(baseline, candidate, "temperature") == False
