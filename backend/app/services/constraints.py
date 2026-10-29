from typing import List, Dict, Union
from app.db.models import Constraint, MetricResult
from app.domain.types import ConstraintOperator, ConstraintEvaluation
from app.schemas.evaluation import MetricStatistics

class ConstraintEngine:

    @staticmethod
    def evaluate(constraints: List[Constraint], metrics: Union[List[MetricResult], Dict[str, MetricStatistics]]) -> List[ConstraintEvaluation]:
        evaluations = []

        is_legacy = isinstance(metrics, list)
        if is_legacy:
            metric_map = {m.metric_name: m.value for m in metrics}
        else:
            metric_map = {k: v for k, v in metrics.items()}

        for c in constraints:
            if is_legacy:
                actual_value = metric_map.get(c.metric_name)
                missing = actual_value is None
                valid = True
                sample_size = 1
            else:
                stats: MetricStatistics = metric_map.get(c.metric_name)
                missing = stats is None
                valid = stats.valid if stats else False
                sample_size = stats.n if stats else 0
                actual_value = stats.mean if stats else None

            if missing:
                evaluations.append(
                    ConstraintEvaluation(
                        metric_name=c.metric_name,
                        passed=False,
                        missing_metric=True,
                        actual_value=None,
                        required_value=c.required_value,
                        operator=ConstraintOperator(c.operator),
                        sample_size=sample_size,
                        evidence_valid=False
                    )
                )
                continue

            if not is_legacy and not valid:
                evaluations.append(
                    ConstraintEvaluation(
                        metric_name=c.metric_name,
                        passed=False,
                        missing_metric=False,
                        actual_value=actual_value,
                        required_value=c.required_value,
                        operator=ConstraintOperator(c.operator),
                        sample_size=sample_size,
                        evidence_valid=False
                    )
                )
                continue

            op = ConstraintOperator(c.operator)
            passed = False

            if op == ConstraintOperator.GTE:
                passed = actual_value >= c.required_value
            elif op == ConstraintOperator.LTE:
                passed = actual_value <= c.required_value
            elif op == ConstraintOperator.EQ:
                passed = actual_value == c.required_value
            elif op == ConstraintOperator.GT:
                passed = actual_value > c.required_value
            elif op == ConstraintOperator.LT:
                passed = actual_value < c.required_value

            evaluations.append(
                ConstraintEvaluation(
                    metric_name=c.metric_name,
                    passed=passed,
                    missing_metric=False,
                    actual_value=actual_value,
                    required_value=c.required_value,
                    operator=op,
                    sample_size=sample_size,
                    evidence_valid=valid
                )
            )

        return evaluations
