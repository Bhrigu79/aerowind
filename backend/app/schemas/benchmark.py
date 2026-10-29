from pydantic import BaseModel, Field
from typing import List, Optional
from app.domain.types import MetricDirection

class BenchmarkMetricDef(BaseModel):
    name: str
    direction: MetricDirection
    unit: str

class BenchmarkContract(BaseModel):
    benchmark_version: str
    workload: str
    dataset: Optional[str] = None
    sample_size: int = Field(gt=0)
    metrics: List[BenchmarkMetricDef]
    evaluation_method: str
