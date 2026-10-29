import json
import time
import os
from datetime import datetime
from typing import List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ExperimentRun, MetricResult, ExperimentVariant
from app.schemas.execution import ExperimentExecutionSpec
from app.services.runner import ExperimentRunner
from app.gateway.gateway import ModelGateway
from app.schemas.gateway import GatewayRequest, MessageRole, Message, TaskType, Provider
from app.domain.types import MetricDirection
from app.services.metrics import MetricService


class RealAIBenchmarkRunner(ExperimentRunner):
    """
    A real AI benchmark runner that executes a defined classification task
    against the Model Gateway, comparing Baseline vs Candidate configurations.
    """

    def __init__(self, gateway: ModelGateway):
        self.gateway = gateway
        # Load dataset
        dataset_path = os.path.join(os.path.dirname(__file__), "..", "benchmarks", "datasets", "sentiment_classification.json")
        with open(dataset_path, "r", encoding="utf-8") as f:
            self.dataset = json.load(f)

    async def execute(self, session: AsyncSession, run: ExperimentRun, spec: ExperimentExecutionSpec = None, **kwargs):
        run.started_at = datetime.utcnow()
        run.status = "running"
        session.add(run)
        await session.commit()

        variant = await session.get(ExperimentVariant, run.variant_id)
        config = variant.system_configuration if variant and variant.system_configuration else {}

        # Determine configuration to use
        # Default baseline config
        temperature = float(config.get("temperature", 0.7))
        max_tokens = int(config.get("max_tokens", 50))
        if "model" not in config:
            raise ValueError("RealAIBenchmarkRunner requires an explicit 'model' in the configuration.")

        model_name = config["model"]

        # Determine sample size, allowing config override to reduce costs during testing
        requested_sample_size = int(config.get("sample_count", len(self.dataset)))

        actual_provider = "gateway_routed"
        actual_model = model_name

        latencies = []
        correct_predictions = 0
        errors = 0
        total_cost = 0.0
        dataset_subset = self.dataset[:requested_sample_size]
        sample_size = len(dataset_subset)

        for item in dataset_subset:
            text = item["text"]
            expected = item["label"]

            system_prompt = "You are a sentiment classifier. Respond ONLY with 'positive' or 'negative'."
            messages = [
                Message(role=MessageRole.SYSTEM, content=system_prompt),
                Message(role=MessageRole.USER, content=f"Classify the sentiment of this text: {text}")
            ]

            req_args = {
                "task_type": TaskType.CLASSIFICATION,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "project_id": variant.project_id,
                "experiment_id": run.experiment_id,
                "allow_fallback": False
            }
            if "provider" in config:
                from app.schemas.gateway import Provider
                try:
                    req_args["preferred_provider"] = Provider(config["provider"].lower())
                except ValueError:
                    pass
            if "model" in config:
                req_args["preferred_model"] = config["model"]

            req = GatewayRequest(**req_args)

            start_time = time.time()
            try:
                # Execute real model call via gateway
                response = await self.gateway.complete(req)
                end_time = time.time()

                if hasattr(response, 'provider') and response.provider:
                    actual_provider = response.provider.value
                if hasattr(response, 'model') and response.model:
                    actual_model = response.model

                latency_ms = (end_time - start_time) * 1000
                latencies.append(latency_ms)

                if hasattr(response, 'usage') and response.usage:
                    cost = response.usage.estimated_cost_usd
                    if cost is not None and total_cost is not None:
                        total_cost += cost
                    else:
                        total_cost = None

                prediction = response.content.strip().lower()
                # Clean up punctuation if the model was chatty
                prediction = "".join(c for c in prediction if c.isalpha())

                if prediction == expected:
                    correct_predictions += 1
            except Exception as e:
                from app.core.exceptions import ProviderUnavailableError, NoProvidersAvailableError
                if isinstance(e, (ProviderUnavailableError, NoProvidersAvailableError)):
                    raise
                errors += 1
                latencies.append(0.0)

        # If all samples failed, we should probably fail explicitly
        if errors == sample_size and sample_size > 0:
            raise RuntimeError("All benchmark samples failed due to provider/model errors.")

        # Calculate final metrics
        accuracy = (correct_predictions / sample_size) * 100.0 if sample_size > 0 else 0.0
        error_rate = errors / sample_size if sample_size > 0 else 0.0

        # If any sample had unavailable cost, mark the overall cost as unavailable (None)
        if total_cost is None:
            avg_cost = None
        else:
            avg_cost = total_cost / sample_size if sample_size > 0 else 0.0

        valid_latencies = [l for l in latencies if l > 0]
        p95_latency = MetricService.calculate_percentile(valid_latencies, 95.0) if valid_latencies else 0.0

        metrics = [
            ("quality_score", accuracy, MetricDirection.HIGHER_IS_BETTER, "score"),
            ("p95_latency_ms", p95_latency, MetricDirection.LOWER_IS_BETTER, "ms"),
            ("cost_per_request_usd", avg_cost, MetricDirection.LOWER_IS_BETTER, "usd"),
            ("error_rate", error_rate, MetricDirection.LOWER_IS_BETTER, "pct")
        ]

        metrics_to_measure = kwargs.get("metrics_to_measure", ["quality_score", "p95_latency_ms", "cost_per_request_usd", "error_rate"])

        for name, value, direction, unit in metrics:
            if name in metrics_to_measure and value is not None:
                m = MetricResult(
                    run_id=run.id,
                    metric_name=name,
                    value=round(value, 4),
                    unit=unit,
                    direction=direction.value,
                    sample_size=sample_size,
                    source="real_ai_benchmark_v1"
                )
                session.add(m)

        # To satisfy point 4: Preserve Measurement Integrity
        # We store metadata in the run itself if needed, or just let evidence pick it up.
        run.completed_at = datetime.utcnow()
        run.success = (errors < sample_size) # Succeeds if not all failed
        run.status = "completed"

        # We also want to capture the exact payload expected by the instruction:
        # Returning specific JSON format.
        result_json = {
            "schema_version": "1",
            "status": "success",
            "benchmark_version": "1.0",
            "dataset_version": "1.0",
            "model_configuration": config,
            "system_configuration": config,
            "provider": actual_provider,
            "requested_provider": config.get("provider"),
            "provider_mismatch": actual_provider != config.get("provider").lower() if config.get("provider") else False,
            "model": actual_model,
            "requested_model": model_name,
            "model_mismatch": actual_model != model_name,
            "sample_size": sample_size,
            "timestamps": {
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None
            },
            "latencies_ms": valid_latencies,
            "metrics": [
                {
                    "name": name,
                    "value": round(value, 4),
                    "unit": unit,
                    "sample_size": sample_size
                }
                for name, value, _, unit in metrics if name in metrics_to_measure and value is not None
            ]
        }

        # Store benchmark artifact in the experiment run config/output
        run.execution_metadata = result_json

        await session.commit()
        return run
