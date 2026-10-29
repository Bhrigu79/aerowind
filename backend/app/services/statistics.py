import math
import statistics
from typing import List, Optional, Tuple, Sequence
import numpy as np
import scipy.stats as stats
from app.schemas.evaluation import MetricObservationSet, MetricStatistics, StatisticalTestResult, ComparisonEvidence, EvidenceStatus
from app.domain.types import MetricDirection


class StatisticalEngine:
    @staticmethod
    def aggregate_metrics(obs_set: MetricObservationSet) -> MetricStatistics:
        n_total = len(obs_set.values)
        if n_total == 0:
            return MetricStatistics(n=0, invalid_count=0, valid=False, is_legacy=obs_set.is_legacy, invalid_reason="Empty values array")

        # Check for NaN / Infinity
        invalid_count = sum(1 for v in obs_set.values if not math.isfinite(v))
        if obs_set.raw_observations:
            for obs_list in obs_set.raw_observations:
                invalid_count += sum(1 for v in obs_list if not math.isfinite(v))

        if invalid_count > 0:
            return MetricStatistics(
                n=n_total - invalid_count,
                invalid_count=invalid_count,
                valid=False,
                is_legacy=obs_set.is_legacy,
                invalid_reason="Contains NaN or Infinity"
            )

        valid_trials = obs_set.values
        valid_n = len(valid_trials)

        mean = sum(valid_trials) / valid_n
        median = statistics.median(valid_trials)
        variance = statistics.variance(valid_trials) if valid_n > 1 else 0.0
        std_dev = math.sqrt(variance)
        min_val = min(valid_trials)
        max_val = max(valid_trials)

        p50 = None
        p95 = None

        # P95 methodology: pool raw observations
        if obs_set.raw_observations is not None:
            pooled = []
            for obs_list in obs_set.raw_observations:
                pooled.extend(obs_list)
            if pooled:
                p50 = float(np.percentile(pooled, 50))
                p95 = float(np.percentile(pooled, 95))

        return MetricStatistics(
            n=valid_n,
            invalid_count=0,
            mean=mean,
            median=median,
            variance=variance,
            std_dev=std_dev,
            min_val=min_val,
            max_val=max_val,
            p50=p50,
            p95=p95,
            valid=True,
            is_legacy=obs_set.is_legacy
        )

    @staticmethod
    def welchs_t_test(
        baseline: MetricObservationSet,
        candidate: MetricObservationSet,
        mpe: float = 0.0,
        alpha_level: float = 0.95,
        direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER
    ) -> StatisticalTestResult:
        base_valid = baseline.values
        cand_valid = candidate.values

        n_base = len(base_valid)
        n_cand = len(cand_valid)

        mean_base = sum(base_valid) / n_base
        mean_cand = sum(cand_valid) / n_cand

        abs_diff = mean_cand - mean_base
        rel_diff = (abs_diff / mean_base) if mean_base != 0 else None

        improvement_delta = (mean_base - mean_cand) if direction == MetricDirection.LOWER_IS_BETTER else (mean_cand - mean_base)

        # We calculate effect_above_mpe based on optimization direction
        effect_above_mpe = (improvement_delta > mpe) if mpe >= 0 else (improvement_delta > 0)

        if n_base < 2 or n_cand < 2:
            return StatisticalTestResult(
                absolute_difference=abs_diff,
                relative_difference=rel_diff,
                mpe=mpe,
                effect_above_mpe=effect_above_mpe,
                statistically_supported=None,
                is_regression=(improvement_delta < 0),
                significant_regression=False,
                status=EvidenceStatus.INSUFFICIENT_SAMPLES
            )

        var_base = statistics.variance(base_valid)
        var_cand = statistics.variance(cand_valid)

        # Degenerate cases
        if var_base == 0 and var_cand == 0:
            is_significant = (improvement_delta > 0)

            if improvement_delta == 0:
                status = EvidenceStatus.NO_OBSERVED_EFFECT
            elif effect_above_mpe:
                status = EvidenceStatus.STATISTICALLY_SUPPORTED
            elif improvement_delta > 0:
                status = EvidenceStatus.BELOW_PRACTICAL_EFFECT
            else:
                status = EvidenceStatus.NOT_STATISTICALLY_SUPPORTED

            return StatisticalTestResult(
                absolute_difference=abs_diff,
                relative_difference=rel_diff,
                mpe=mpe,
                effect_above_mpe=effect_above_mpe,
                statistically_supported=is_significant,
                is_regression=(improvement_delta < 0),
                significant_regression=(improvement_delta < 0), # zero variance case
                status=status
            )

        try:
            res = stats.ttest_ind(cand_valid, base_valid, equal_var=False)
            t_stat = float(res.statistic) if not np.isnan(res.statistic) else None
            p_val = float(res.pvalue) if not np.isnan(res.pvalue) else None
            df = float(res.df) if not np.isnan(res.df) else None

            ci_low, ci_high = None, None
            if df is not None and df > 0:
                ci = res.confidence_interval(confidence_level=alpha_level)
                ci_low, ci_high = float(ci.low), float(ci.high)

            # Since ttest_ind is two-sided and our hypothesis implies candidate > baseline (or candidate < baseline)
            is_significant = False
            sig_regression = False
            if p_val is not None:
                is_significant = bool((p_val / 2 < (1 - alpha_level)) and (improvement_delta > 0))
                sig_regression = bool((p_val / 2 < (1 - alpha_level)) and (improvement_delta < 0))

                if is_significant:
                    status = EvidenceStatus.STATISTICALLY_SUPPORTED if effect_above_mpe else EvidenceStatus.BELOW_PRACTICAL_EFFECT
                elif improvement_delta == 0:
                    status = EvidenceStatus.NO_OBSERVED_EFFECT
                else:
                    status = EvidenceStatus.NOT_STATISTICALLY_SUPPORTED
            else:
                is_significant = None
                status = EvidenceStatus.INVALID_DATA

            return StatisticalTestResult(
                absolute_difference=abs_diff,
                relative_difference=rel_diff,
                mpe=mpe,
                effect_above_mpe=effect_above_mpe,
                statistically_supported=is_significant,
                is_regression=(improvement_delta < 0),
                significant_regression=sig_regression,
                test_statistic=t_stat,
                degrees_of_freedom=df,
                p_value=p_val,
                confidence_interval_lower=ci_low,
                confidence_interval_upper=ci_high,
                status=status
            )
        except Exception:
            return StatisticalTestResult(
                absolute_difference=abs_diff,
                relative_difference=rel_diff,
                mpe=mpe,
                effect_above_mpe=effect_above_mpe,
                statistically_supported=None,
                is_regression=(improvement_delta < 0),
                significant_regression=False,
                status=EvidenceStatus.INVALID_DATA
            )

    @staticmethod
    def wilson_score_interval(successes: int, trials: int, confidence_level: float = 0.95) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        if trials <= 0 or successes < 0 or successes > trials or not (0 < confidence_level < 1):
            return None, None, None

        p_hat = successes / trials
        z = statistics.NormalDist().inv_cdf((1 + confidence_level) / 2)

        denominator = 1 + z**2 / trials
        center = p_hat + z**2 / (2 * trials)
        spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * trials)) / trials)

        lower = (center - spread) / denominator
        upper = (center + spread) / denominator
        return p_hat, lower, upper

    @staticmethod
    def evaluate_comparison(
        baseline: MetricObservationSet,
        candidate: MetricObservationSet,
        mpe: float = 0.0,
        alpha_level: float = 0.95,
        direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER
    ) -> ComparisonEvidence:
        b_stats = StatisticalEngine.aggregate_metrics(baseline)
        c_stats = StatisticalEngine.aggregate_metrics(candidate)

        if not b_stats.valid or not c_stats.valid:
            test_res = StatisticalTestResult(status=EvidenceStatus.INVALID_DATA)
            return ComparisonEvidence(
                baseline_stats=b_stats,
                candidate_stats=c_stats,
                comparison=test_res
            )

        if baseline.is_legacy or candidate.is_legacy:
            # Legacy Phase 16 records
            abs_diff = None
            rel_diff = None
            if b_stats.mean is not None and c_stats.mean is not None:
                abs_diff = c_stats.mean - b_stats.mean
                if b_stats.mean != 0:
                    rel_diff = abs_diff / b_stats.mean

            test_res = StatisticalTestResult(
                absolute_difference=abs_diff,
                relative_difference=rel_diff,
                mpe=mpe,
                status=EvidenceStatus.LEGACY
            )
        elif b_stats.n < 2 or c_stats.n < 2:
            test_res = StatisticalTestResult(status=EvidenceStatus.INSUFFICIENT_SAMPLES)
        else:
            test_res = StatisticalEngine.welchs_t_test(baseline, candidate, mpe, alpha_level, direction)

        return ComparisonEvidence(
            baseline_stats=b_stats,
            candidate_stats=c_stats,
            comparison=test_res
        )
