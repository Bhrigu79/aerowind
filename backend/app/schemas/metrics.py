"""
AEROWIND Pydantic Schemas — Metrics
=====================================
Metrics schemas for the observability and dashboard layer.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TimeSeriesPoint(BaseModel):
    timestamp: datetime
    value: float
    label: str | None = None


class ProviderUsageStats(BaseModel):
    provider: str
    requests: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    avg_latency_ms: float
    p95_latency_ms: float
    failures: int
    error_rate: float = 0.0


class SystemMetrics(BaseModel):
    """Dashboard-level system metrics."""

    # Global
    total_projects: int = 0
    active_experiments: int = 0
    total_experiments: int = 0
    total_hypotheses: int = 0
    confirmed_hypotheses: int = 0

    # Performance
    global_avg_latency_ms: float = 0.0
    global_p95_latency_ms: float = 0.0
    global_error_rate: float = 0.0

    # Cost
    total_estimated_cost_usd: float = 0.0
    total_tokens_used: int = 0

    # Provider breakdown
    provider_stats: list[ProviderUsageStats] = []

    # Time series (for charts)
    latency_series: list[TimeSeriesPoint] = []
    cost_series: list[TimeSeriesPoint] = []
    quality_series: list[TimeSeriesPoint] = []
