from typing import List, Dict, Any
from app.db.models import Constraint, MetricResult
from app.domain.types import ConstraintOperator

class ObjectiveProgressService:
    @staticmethod
    def calculate_progress(
        constraints: List[Constraint],
        baseline_metrics: List[MetricResult],
        current_metrics: List[MetricResult]
    ) -> Dict[str, Any]:
        """
        Calculate progress from baseline to current for each constraint.
        """
        base_map = {m.metric_name: m.value for m in baseline_metrics}
        curr_map = {m.metric_name: m.value for m in current_metrics}

        progress = {}
        all_passed = True

        for c in constraints:
            base_val = base_map.get(c.metric_name)
            curr_val = curr_map.get(c.metric_name)

            if curr_val is None:
                all_passed = False
                progress[c.metric_name] = {
                    "status": "failing (missing)",
                    "passed": False,
                    "gap": None
                }
                continue

            op = ConstraintOperator(c.operator)
            passed = False

            if op == ConstraintOperator.GTE:
                passed = curr_val >= c.required_value
                gap = c.required_value - curr_val if not passed else 0
            elif op == ConstraintOperator.LTE:
                passed = curr_val <= c.required_value
                gap = curr_val - c.required_value if not passed else 0
            elif op == ConstraintOperator.EQ:
                passed = curr_val == c.required_value
                gap = abs(curr_val - c.required_value) if not passed else 0
            elif op == ConstraintOperator.GT:
                passed = curr_val > c.required_value
                gap = c.required_value - curr_val if not passed else 0
            elif op == ConstraintOperator.LT:
                passed = curr_val < c.required_value
                gap = curr_val - c.required_value if not passed else 0

            if not passed:
                all_passed = False

            improvement_from_baseline = None
            if base_val is not None:
                improvement_from_baseline = curr_val - base_val

            progress[c.metric_name] = {
                "baseline": base_val,
                "current": curr_val,
                "target": c.required_value,
                "status": "passing" if passed else "failing",
                "passed": passed,
                "gap": max(0, gap),
                "improvement_from_baseline": improvement_from_baseline
            }

        return {
            "all_passed": all_passed,
            "metrics_progress": progress
        }
