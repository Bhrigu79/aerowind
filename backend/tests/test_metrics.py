import pytest
from app.services.metrics import MetricService
from app.domain.types import MetricDirection

def test_calculate_mean():
    assert MetricService.calculate_mean([1.0, 2.0, 3.0]) == 2.0
    assert MetricService.calculate_mean([]) == 0.0

def test_calculate_percentile():
    data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert MetricService.calculate_percentile(data, 50.0) == 5.5
    assert MetricService.calculate_percentile(data, 90.0) == 9.1
    assert MetricService.calculate_percentile(data, 99.0) == 9.91
    assert MetricService.calculate_percentile([], 99.0) == 0.0

def test_calculate_percentage_change():
    # Lower is better (latency)
    # 100 -> 80 is a -20% change
    change = MetricService.calculate_percentage_change(100.0, 80.0, MetricDirection.LOWER_IS_BETTER)
    assert change == -20.0

    # Higher is better (quality)
    # 80 -> 100 is a +25% change
    change2 = MetricService.calculate_percentage_change(80.0, 100.0, MetricDirection.HIGHER_IS_BETTER)
    assert change2 == 25.0

    # Baseline 0
    assert MetricService.calculate_percentage_change(0.0, 10.0, MetricDirection.HIGHER_IS_BETTER) == 0.0

def test_aggregate_metrics():
    data = [10.0, 20.0, 30.0, 40.0, 50.0]
    agg = MetricService.aggregate_metrics(data, "test_metric")
    assert agg["mean"] == 30.0
    assert agg["median"] == 30.0
    assert agg["p50"] == 30.0
    assert agg["p95"] == 48.0
    assert agg["p99"] == 49.6
