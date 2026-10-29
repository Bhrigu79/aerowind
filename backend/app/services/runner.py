import asyncio
import json
import os
import shlex
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import ExperimentRun, MetricResult
from app.domain.types import RunnerType, MetricDirection
from datetime import datetime
import random
from app.schemas.execution import ExperimentExecutionSpec

class ExecutionFailure(Exception):
    def __init__(self, failure_type: str, stage: str, message: str, recoverable: bool = False):
        self.failure_type = failure_type
        self.stage = stage
        self.message = message
        self.recoverable = recoverable
        super().__init__(self.message)

class ExperimentRunner:
    async def execute(self, session: AsyncSession, run: ExperimentRun, spec: ExperimentExecutionSpec = None, **kwargs):
        raise NotImplementedError

class SyntheticExperimentRunner(ExperimentRunner):
    """
    A robust, deterministic mock runner simulating a Customer Support AI benchmark.
    Produces synthetic measurements based on a fixed evaluation dataset and trade-off formulas.
    """
    async def execute(self, session: AsyncSession, run: ExperimentRun, spec: ExperimentExecutionSpec = None, **kwargs):
        run.started_at = datetime.utcnow()
        run.status = "running"

        metrics_to_measure = kwargs.get("metrics_to_measure", ["quality_score", "p95_latency_ms", "cost_per_request_usd", "error_rate"])

        config = run.variant.system_configuration if run.variant and run.variant.system_configuration else {}

        temperature = float(config.get("temperature", 0.7))
        model = str(config.get("model", "default")).lower()
        use_cot = bool(config.get("chain_of_thought", False))
        prompt_strategy = str(config.get("prompt_strategy", "direct")).lower()
        few_shot_count = int(config.get("few_shot_count", 0))
        retrieval_enabled = bool(config.get("retrieval_enabled", False))
        pipeline_mode = str(config.get("pipeline_mode", "single")).lower()
        max_tokens = int(config.get("max_tokens", 512))

        # Customer Support Benchmark Evaluation Dataset v1.0
        # Categorized by customer intent mapping to required AI capabilities.
        dataset = [
            {"id": "t1", "cat": "factual", "intent": "product_questions", "base_tokens": 100, "req_tokens": 150},
            {"id": "t2", "cat": "factual", "intent": "policy_questions", "base_tokens": 120, "req_tokens": 150},
            {"id": "t3", "cat": "factual", "intent": "factual_questions", "base_tokens": 90, "req_tokens": 100},
            {"id": "t4", "cat": "reasoning", "intent": "multi_step_reasoning", "base_tokens": 300, "req_tokens": 300},
            {"id": "t5", "cat": "reasoning", "intent": "troubleshooting", "base_tokens": 350, "req_tokens": 300},
            {"id": "t6", "cat": "formatting", "intent": "ambiguous_requests", "base_tokens": 50, "req_tokens": 100},
            {"id": "t7", "cat": "formatting", "intent": "routing_classification", "base_tokens": 80, "req_tokens": 120},
            {"id": "t8", "cat": "formatting", "intent": "json_extraction", "base_tokens": 60, "req_tokens": 100},
            {"id": "t9", "cat": "long_form", "intent": "email_drafting", "base_tokens": 200, "req_tokens": 350},
            {"id": "t10", "cat": "long_form", "intent": "escalation_summary", "base_tokens": 250, "req_tokens": 400},
        ]

        # Model performance characteristics
        is_large = "70b" in model or "large" in model
        base_model_quality = 0.9 if is_large else 0.7
        cost_per_1k_tokens = 0.015 if is_large else 0.002
        latency_per_token_ms = 12.0 if is_large else 4.0

        total_quality = 0.0
        latencies = []
        total_cost = 0.0
        errors = 0

        for task in dataset:
            q = base_model_quality
            lat = 0.0
            tokens_in = task["base_tokens"]
            tokens_out = min(max_tokens, task["req_tokens"])

            # 1. Retrieval Trade-off
            if task["cat"] == "factual":
                if retrieval_enabled:
                    q += 0.3
                    tokens_in += 500  # Retrieval context adds tokens
                    lat += 890.0      # Retrieval network call overhead
                else:
                    q -= 0.5  # Hallucination

            # 2. Reasoning Trade-off
            if task["cat"] == "reasoning":
                if use_cot or pipeline_mode == "draft_critique":
                    q += 0.35
                    tokens_out = min(max_tokens, int(task["req_tokens"] * 1.5))
                    if pipeline_mode == "draft_critique":
                        lat += 1000.0  # Second pass overhead
                        tokens_in *= 2
                        tokens_out *= 2
                else:
                    q -= 0.4

            # 3. Formatting Trade-off
            if task["cat"] == "formatting":
                if prompt_strategy == "structured":
                    q += 0.2
                else:
                    q -= 0.2
                if few_shot_count > 0:
                    q += min(0.3, few_shot_count * 0.1)
                    tokens_in += few_shot_count * 150
                else:
                    q -= 0.2

            # 4. Long Form Trade-off
            if task["cat"] == "long_form":
                if max_tokens < task["req_tokens"]:
                    # Penalize for truncating the required answer
                    q -= 0.5 * (1.0 - (max_tokens / task["req_tokens"]))

            # Temperature penalty
            if temperature > 0.7 and task["cat"] in ["factual", "reasoning", "formatting"]:
                q -= (temperature - 0.7) * 0.5

            if temperature > 0.9:
                errors += 1

            # Clamp quality
            q = max(0.0, min(1.0, q))
            total_quality += q

            # Calculate task cost & latency
            task_cost = ((tokens_in + tokens_out) / 1000.0) * cost_per_1k_tokens
            total_cost += task_cost

            task_lat = lat + (tokens_in * 0.5) + (tokens_out * latency_per_token_ms)
            latencies.append(task_lat)

        # Aggregate metrics
        avg_quality = (total_quality / len(dataset)) * 100.0
        # P95 latency approximation
        latencies.sort()
        p95_idx = int(len(latencies) * 0.95)
        p95_latency = latencies[p95_idx] if latencies else 0.0
        avg_cost = total_cost / len(dataset)
        error_rate = errors / len(dataset)

        for metric_name in metrics_to_measure:
            if metric_name == "quality_score":
                value, direction, unit = avg_quality, MetricDirection.HIGHER_IS_BETTER, "%"
            elif metric_name == "p95_latency_ms":
                value, direction, unit = p95_latency, MetricDirection.LOWER_IS_BETTER, "ms"
            elif metric_name == "cost_per_request_usd":
                value, direction, unit = avg_cost, MetricDirection.LOWER_IS_BETTER, "usd"
            elif metric_name == "error_rate":
                value, direction, unit = error_rate, MetricDirection.LOWER_IS_BETTER, "pct"
            else:
                value, direction, unit = 0.0, MetricDirection.HIGHER_IS_BETTER, "unknown"

            m = MetricResult(
                run_id=run.id,
                metric_name=metric_name,
                value=round(value, 4),
                unit=unit,
                direction=direction.value,
                sample_size=len(dataset),
                source=run.runner_type if hasattr(run, 'runner_type') and run.runner_type else RunnerType.SYNTHETIC.value
            )
            session.add(m)

        run.completed_at = datetime.utcnow()
        run.success = True
        run.status = "completed"
        return run


class LocalIsolatedRunner(ExperimentRunner):
    """
    A local runner that executes the spec in an isolated Docker container.
    Enforces resource limits, captures stdout/stderr, and prevents host access.
    """
    async def execute(self, session: AsyncSession, run: ExperimentRun, spec: ExperimentExecutionSpec = None, **kwargs):
        if not spec:
            raise ValueError("ExperimentExecutionSpec is required for LocalIsolatedRunner")

        run.started_at = datetime.utcnow()
        run.status = "running"
        await session.commit()

        try:
            # 1. Security boundary checks
            if any("/" in k or "=" in k for k in spec.environment.keys()):
                raise ExecutionFailure("VALIDATION_ERROR", "EXECUTION", "Invalid environment variables")

            # 2. Build docker run command explicitly to prevent shell injection
            container_name = f"aerowind_run_{run.id[:8]}"
            cmd = [
                "docker", "run", "--rm",
                "--name", container_name,
                "--network", "none", # Total isolation, no network unless explicitly allowed
                "--cpus", str(spec.resource_limits.cpu_cores),
                "--memory", f"{spec.resource_limits.memory_mb}m",
            ]

            for k, v in spec.environment.items():
                cmd.extend(["-e", f"{k}={v}"])

            # Mount artifacts in a read-only way or explicit scratch space
            # For this implementation, we just mock the mount structure for safety
            # -v /tmp/aerowind/{run.id}:/workspace:rw

            # Assume workload dictates the base image
            image = "python:3.11-slim" if spec.workload == "python" else "alpine:latest"
            cmd.append(image)

            # Add the explicit entrypoint
            cmd.extend(spec.entrypoint)

            # 3. Execute with timeout
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=spec.resource_limits.timeout_seconds)
            except asyncio.TimeoutError:
                # Kill container
                kill_proc = await asyncio.create_subprocess_exec("docker", "rm", "-f", container_name)
                await kill_proc.communicate()
                raise ExecutionFailure("TIMEOUT", "EXECUTION", f"Execution exceeded {spec.resource_limits.timeout_seconds}s")

            if process.returncode != 0:
                err_msg = stderr.decode()[:1000]
                raise ExecutionFailure("PROCESS_ERROR", "EXECUTION", f"Process failed with code {process.returncode}: {err_msg}")

            # Simulate parsing metric results from stdout or an output artifact
            run.execution_metadata = {
                "stdout_preview": stdout.decode()[:500],
                "exit_code": process.returncode
            }

            # Removed fake metric generation to satisfy P0 - Remove all production fake-metric fallbacks
            # If the container did not emit standard format metrics, we rely on the parser (not implemented here) or leave them empty.
            run.success = True

        except ExecutionFailure as ef:
            run.success = False
            run.error_info = json.dumps({"type": ef.failure_type, "message": ef.message})
        except Exception as e:
            run.success = False
            run.error_info = json.dumps({"type": "UNEXPECTED", "message": str(e)})

        run.completed_at = datetime.utcnow()
        run.status = "completed" if run.success else "failed"
        await session.commit()
        return run
