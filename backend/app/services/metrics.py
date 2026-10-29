from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import MetricResult, ExperimentRun
from app.domain.types import MetricDirection

class MetricService:
    @staticmethod
    async def record_metric(
        session: AsyncSession,
        run_id: str,
        name: str,
        value: float,
        unit: str,
        direction: MetricDirection,
        sample_size: int,
        source: str
    ) -> MetricResult:
        metric = MetricResult(
            run_id=run_id,
            metric_name=name,
            value=value,
            unit=unit,
            direction=direction.value,
            sample_size=sample_size,
            source=source
        )
        session.add(metric)
        return metric

    @staticmethod
    def calculate_percentile(data: list[float], percentile: float) -> float:
        if not data:
            return 0.0
        data.sort()
        k = (len(data) - 1) * (percentile / 100.0)
        f = int(k)
        c = f + 1
        if c >= len(data):
            return float(data[-1])
        if f == c:
            return float(data[int(k)])
        d0 = data[f] * (c - k)
        d1 = data[c] * (k - f)
        return float(d0 + d1)

    @staticmethod
    def calculate_mean(data: list[float]) -> float:
        if not data:
            return 0.0
        return sum(data) / len(data)

    @staticmethod
    def calculate_median(data: list[float]) -> float:
        return MetricService.calculate_percentile(data, 50.0)

    @staticmethod
    def calculate_percentage_change(baseline: float, candidate: float, direction: MetricDirection) -> float:
        if baseline == 0:
            return 0.0
        diff = candidate - baseline
        change = (diff / abs(baseline)) * 100.0
        return float(change)

    @staticmethod
    def aggregate_metrics(raw_data: list[float], metric_name: str) -> dict[str, float]:
        """Calculates basic summary statistics for a given list of raw data points."""
        return {
            "mean": MetricService.calculate_mean(raw_data),
            "median": MetricService.calculate_median(raw_data),
            "p50": MetricService.calculate_percentile(raw_data, 50.0),
            "p95": MetricService.calculate_percentile(raw_data, 95.0),
            "p99": MetricService.calculate_percentile(raw_data, 99.0)
        }
