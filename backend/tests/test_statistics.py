import math
import pytest
from app.services.statistics import StatisticalEngine
from app.schemas.evaluation import EvidenceStatus, MetricObservationSet

def _obs(values, raw=None, legacy=False):
    return MetricObservationSet(values=values, raw_observations=raw, is_legacy=legacy)

def test_A_identical_constant_arrays():
    res = StatisticalEngine.evaluate_comparison(_obs([90, 90, 90]), _obs([90, 90, 90]))
    assert res.comparison.status == EvidenceStatus.NO_OBSERVED_EFFECT
    assert res.comparison.absolute_difference == 0.0

def test_B_different_constant_arrays():
    res = StatisticalEngine.evaluate_comparison(_obs([90, 90, 90]), _obs([95, 95, 95]), mpe=1.0)
    assert res.comparison.status == EvidenceStatus.STATISTICALLY_SUPPORTED
    assert res.comparison.statistically_supported is True
    assert res.comparison.absolute_difference == 5.0

    res_below = StatisticalEngine.evaluate_comparison(_obs([90, 90, 90]), _obs([90.5, 90.5, 90.5]), mpe=1.0)
    assert res_below.comparison.status == EvidenceStatus.BELOW_PRACTICAL_EFFECT
    assert res_below.comparison.statistically_supported is True

def test_C_one_constant_one_variable():
    res = StatisticalEngine.evaluate_comparison(_obs([90, 90, 90]), _obs([94, 95, 96]), mpe=1.0)
    assert res.comparison.status in [EvidenceStatus.STATISTICALLY_SUPPORTED, EvidenceStatus.BELOW_PRACTICAL_EFFECT]
    assert res.comparison.absolute_difference == 5.0

def test_D_insufficient_samples():
    res = StatisticalEngine.evaluate_comparison(_obs([90]), _obs([95]))
    assert res.comparison.status == EvidenceStatus.INSUFFICIENT_SAMPLES

    res = StatisticalEngine.evaluate_comparison(_obs([90, 90]), _obs([95]))
    assert res.comparison.status == EvidenceStatus.INSUFFICIENT_SAMPLES

def test_E_NaN():
    res = StatisticalEngine.evaluate_comparison(_obs([90, float('nan'), 90]), _obs([95, 95, 95]))
    # NaN is rejected, so invalid_count is 1 and it's marked invalid
    assert not res.baseline_stats.valid
    assert res.baseline_stats.invalid_count == 1
    assert res.baseline_stats.n == 2
    assert res.comparison.status == EvidenceStatus.INVALID_DATA

    res2 = StatisticalEngine.evaluate_comparison(_obs([float('nan')]), _obs([95, 95]))
    assert res2.comparison.status == EvidenceStatus.INVALID_DATA

def test_F_infinity():
    res = StatisticalEngine.evaluate_comparison(_obs([90, 90]), _obs([95, float('inf'), 95]))
    assert not res.candidate_stats.valid
    assert res.candidate_stats.invalid_count == 1
    assert res.candidate_stats.n == 2
    assert res.comparison.status == EvidenceStatus.INVALID_DATA

    res_neg = StatisticalEngine.evaluate_comparison(_obs([90, 90]), _obs([95, float('-inf'), 95]))
    assert not res_neg.candidate_stats.valid
    assert res_neg.comparison.status == EvidenceStatus.INVALID_DATA

def test_G_zero_observations():
    res = StatisticalEngine.evaluate_comparison(_obs([]), _obs([]))
    assert res.comparison.status == EvidenceStatus.INVALID_DATA
    assert not res.baseline_stats.valid

def test_H_negative_values():
    res = StatisticalEngine.evaluate_comparison(_obs([-10, -5, 0]), _obs([0, 5, 10]))
    assert res.comparison.absolute_difference == 10.0
    assert res.baseline_stats.mean == -5.0

def test_I_J_K_L_P50_P95():
    trial1 = [10, 20, 30]
    trial2 = [40, 50, 60]
    raw = [trial1, trial2]
    stats = StatisticalEngine.aggregate_metrics(_obs([20, 50], raw=raw))
    assert stats.p50 == 35.0
    assert stats.p95 == 57.5

    t1_p95 = 28.0
    t2_p95 = 58.0
    avg_p95 = (t1_p95 + t2_p95) / 2
    assert stats.p95 != avg_p95

    stats_no_raw = StatisticalEngine.aggregate_metrics(_obs([20, 50]))
    assert stats_no_raw.p95 is None

def test_M_Welch_normal_case():
    res = StatisticalEngine.evaluate_comparison(_obs([80, 82, 81]), _obs([90, 92, 91]), mpe=1.0)
    assert res.comparison.status == EvidenceStatus.STATISTICALLY_SUPPORTED
    assert res.comparison.statistically_supported is True
    assert res.comparison.test_statistic is not None
    assert res.comparison.p_value is not None

def test_N_Welch_zero_variance():
    res = StatisticalEngine.evaluate_comparison(_obs([90, 90, 90]), _obs([90, 90, 90]))
    assert res.comparison.status == EvidenceStatus.NO_OBSERVED_EFFECT
    assert res.comparison.test_statistic is None

def test_O_Welch_insufficient_samples():
    res = StatisticalEngine.welchs_t_test(_obs([90]), _obs([95]))
    assert res.status == EvidenceStatus.INSUFFICIENT_SAMPLES

def test_P_Wilson_normal():
    p_hat, lower, upper = StatisticalEngine.wilson_score_interval(80, 100)
    assert p_hat == 0.8
    assert 0.70 < lower < 0.80
    assert 0.80 < upper < 0.90

def test_Q_Wilson_zero_trials():
    p, l, u = StatisticalEngine.wilson_score_interval(0, 0)
    assert p is None

def test_R_Wilson_invalid_successes():
    p, l, u = StatisticalEngine.wilson_score_interval(-1, 100)
    assert p is None
    p, l, u = StatisticalEngine.wilson_score_interval(101, 100)
    assert p is None

def test_S_Wilson_confidence_level():
    p, l, u = StatisticalEngine.wilson_score_interval(80, 100, -0.1)
    assert p is None
    p, l, u = StatisticalEngine.wilson_score_interval(80, 100, 1.1)
    assert p is None

def test_T_MPE_below_effect():
    res = StatisticalEngine.evaluate_comparison(_obs([90, 91, 92]), _obs([93, 94, 95]), mpe=1.0)
    assert res.comparison.status == EvidenceStatus.STATISTICALLY_SUPPORTED
    assert res.comparison.statistically_supported is True

def test_U_MPE_above_effect():
    res = StatisticalEngine.evaluate_comparison(_obs([90, 90, 90]), _obs([91, 91, 91]), mpe=5.0)
    # Effect is 1.0. MPE is 5.0. It is statistically significant (var 0), but below MPE
    assert res.comparison.status == EvidenceStatus.BELOW_PRACTICAL_EFFECT
    assert res.comparison.statistically_supported is True

def test_V_zero_effect():
    res = StatisticalEngine.evaluate_comparison(_obs([90, 91, 92]), _obs([90, 91, 92]), mpe=1.0)
    assert res.comparison.status == EvidenceStatus.NO_OBSERVED_EFFECT
    assert res.comparison.statistically_supported is False

def test_W_negative_effect():
    res = StatisticalEngine.evaluate_comparison(_obs([90, 91, 92]), _obs([80, 81, 82]), mpe=1.0)
    assert res.comparison.status == EvidenceStatus.NOT_STATISTICALLY_SUPPORTED
    assert res.comparison.statistically_supported is False

def test_X_legacy_metric_without_trial_provenance():
    # If a boolean is NOT passed but the struct has legacy=True, it works.
    res = StatisticalEngine.evaluate_comparison(_obs([90], legacy=True), _obs([95], legacy=True))
    assert res.comparison.status == EvidenceStatus.LEGACY

def test_Y_trial_metric_with_explicit_provenance():
    res = StatisticalEngine.evaluate_comparison(_obs([90, 91, 92]), _obs([95, 96, 97]))
    assert res.comparison.status == EvidenceStatus.STATISTICALLY_SUPPORTED

def test_Z_comparison_unequal_sample_sizes():
    res = StatisticalEngine.evaluate_comparison(_obs([90, 91, 92]), _obs([95, 96, 97, 98, 99]))
    assert res.comparison.status == EvidenceStatus.STATISTICALLY_SUPPORTED
    assert res.baseline_stats.n == 3
    assert res.candidate_stats.n == 5
