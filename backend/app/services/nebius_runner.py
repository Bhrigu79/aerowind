import asyncio
import json
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import ExperimentRun, MetricResult
from app.domain.types import RunnerType, MetricDirection
from app.schemas.execution import ExperimentExecutionSpec
from app.services.runner import ExperimentRunner, ExecutionFailure
from app.core.config import settings

try:
    from nebius.sdk import SDK
    from nebius.api.nebius.ai.v1 import (
        JobServiceClient,
        JobSpec,
        CreateJobRequest,
        JobStatus,
        GetJobRequest
    )
    from nebius.api.nebius.common.v1 import ResourceMetadata
except ImportError:
    SDK = None

class NebiusExperimentRunner(ExperimentRunner):
    def __init__(self):
        if not settings.NEBIUS_EXEC_ENABLED:
            raise ValueError("Nebius execution is not enabled in configuration")
        if not SDK:
            raise ImportError("Nebius Python SDK is not installed")
        if not settings.NEBIUS_EXEC_SERVICE_ACCOUNT_ID:
            raise ValueError("Nebius service account configuration is missing")

        self.sdk = SDK(
            service_account_id=settings.NEBIUS_EXEC_SERVICE_ACCOUNT_ID,
            service_account_public_key_id=settings.NEBIUS_EXEC_PUBLIC_KEY_ID,
            service_account_private_key_file_name=settings.NEBIUS_EXEC_PRIVATE_KEY_FILE
        )
        self.client = self.sdk.client(JobServiceClient)

    async def execute(self, session: AsyncSession, run: ExperimentRun, spec: ExperimentExecutionSpec = None, **kwargs):
        if not spec:
            raise ValueError("Nebius runner requires an ExperimentExecutionSpec")

        run.started_at = datetime.utcnow()
        run.status = "running"
        await session.commit()

        try:
            # Construct Environment Variables
            env_vars = []
            for k, v in spec.environment.items():
                env_vars.append(JobSpec.EnvironmentVariable(name=k, value=str(v)))

            # Map into JobSpec
            job_spec = JobSpec(
                image=settings.NEBIUS_EXEC_CONTAINER_REGISTRY + ":" + spec.workload,
                container_command=" ".join(spec.entrypoint),
                environment_variables=env_vars,
            )

            # TODO: add GPU preset platform and preset fields appropriately once documented.

            req = CreateJobRequest(
                metadata=ResourceMetadata(
                    parent_id=settings.NEBIUS_EXEC_PROJECT_ID,
                    name=f"aerowind-exp-{run.id[:8]}"
                ),
                spec=job_spec
            )

            # Submit Job
            operation = await self.client.create(req)

            # Save job identifier immediately
            new_meta = dict(run.execution_metadata or {})
            new_meta["nebius_operation_id"] = operation.id
            run.execution_metadata = new_meta
            await session.commit()

            # Wait for execution with explicit timeout
            timeout = spec.resource_limits.timeout_seconds or settings.NEBIUS_EXEC_DEFAULT_TIMEOUT_SECONDS
            await asyncio.wait_for(operation.wait(), timeout=timeout)

            # Fetch the final Job status
            get_req = GetJobRequest(id=operation.resource_id)
            job = await self.client.get(get_req)

            # Record provenance
            new_meta = dict(run.execution_metadata or {})
            new_meta.update({
                "runner": "nebius",
                "nebius_job_id": job.id,
                "project_id": settings.NEBIUS_EXEC_PROJECT_ID,
                "image": job_spec.image,
                "final_state": str(job.status.state) if job.status else "UNKNOWN",
                "state_details": str(job.status.state_details) if job.status and job.status.state_details else None
            })
            run.execution_metadata = new_meta

            run.status = "completed"
            run.completed_at = datetime.utcnow()

            # Log retrieval: Since native log retrieval via AI SDK is unavailable natively right now,
            # we must explicitly fail rather than inventing metrics.
            raise ExecutionFailure("EXECUTION_UNAVAILABLE", "EXECUTION", "Log retrieval mechanism from Nebius not yet implemented.")

            # The following would parse logs if we had them:
            # self._parse_and_store_metrics(session, run, raw_logs)

        except asyncio.TimeoutError:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            run.error_info = json.dumps({"type": "TIMEOUT", "stage": "EXECUTION", "message": "Nebius job exceeded timeout"})
            await session.commit()
            raise ExecutionFailure("TIMEOUT", "EXECUTION", "Nebius job exceeded timeout")
        except ExecutionFailure as ef:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            run.error_info = json.dumps({"type": ef.failure_type, "stage": ef.stage, "message": ef.message})
            await session.commit()
            raise
        except Exception as e:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            run.error_info = json.dumps({"type": "INFRASTRUCTURE_ERROR", "stage": "EXECUTION", "message": str(e)})
            await session.commit()
            raise ExecutionFailure("INFRASTRUCTURE_ERROR", "EXECUTION", str(e))

    def _parse_and_store_metrics(self, session: AsyncSession, run: ExperimentRun, raw_logs: str):
        import json
        try:
            # We look for the JSON payload in the logs
            # For simplicity, we assume the entire log is the JSON or we find the JSON block.
            try:
                data = json.loads(raw_logs)
            except json.JSONDecodeError:
                # Attempt to extract if it's embedded
                import re
                match = re.search(r'\{.*"schema_version".*\}', raw_logs, re.DOTALL)
                if not match:
                    raise ExecutionFailure("INVALID_OUTPUT", "PARSING", "No structured metric JSON found in logs")
                data = json.loads(match.group(0))

            if data.get("schema_version") != "1":
                raise ExecutionFailure("INVALID_OUTPUT", "PARSING", "Invalid schema version")

            metrics = data.get("metrics", [])
            if not metrics:
                raise ExecutionFailure("MISSING_METRICS", "PARSING", "JSON contains no metrics array")

            for m in metrics:
                direction = MetricDirection.LOWER_IS_BETTER if "latency" in m.get("name", "").lower() else MetricDirection.HIGHER_IS_BETTER
                mr = MetricResult(
                    run_id=run.id,
                    metric_name=m["name"],
                    value=float(m["value"]),
                    unit=m.get("unit", "unknown"),
                    sample_size=int(m.get("sample_size", 1)),
                    source="nebius",
                    direction=direction
                )
                session.add(mr)

        except ExecutionFailure:
            raise
        except Exception as e:
            raise ExecutionFailure("INVALID_OUTPUT", "PARSING", f"Failed to parse metrics: {str(e)}")
