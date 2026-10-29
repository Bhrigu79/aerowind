import pytest
from app.schemas.execution import ExperimentExecutionSpec, ResourceLimits
from pydantic import ValidationError

def test_execution_spec_validation():
    # Valid spec
    spec = ExperimentExecutionSpec(
        experiment_id="exp1",
        variant_id="var1",
        runner_type="local",
        workload="python",
        entrypoint=["python", "-c", "print('hello')"]
    )
    assert spec.resource_limits.timeout_seconds == 300

    # Invalid entrypoint (shell characters)
    with pytest.raises(ValidationError):
        ExperimentExecutionSpec(
            experiment_id="exp1",
            variant_id="var1",
            runner_type="local",
            workload="python",
            entrypoint=["sh", "-c", "echo hello"]
        )

    with pytest.raises(ValidationError):
        ExperimentExecutionSpec(
            experiment_id="exp1",
            variant_id="var1",
            runner_type="local",
            workload="python",
            entrypoint=["python", "script.py", "&&", "rm", "-rf", "/"]
        )

    # Invalid artifact paths
    with pytest.raises(ValidationError):
        ExperimentExecutionSpec(
            experiment_id="exp1",
            variant_id="var1",
            runner_type="local",
            workload="python",
            entrypoint=["python", "script.py"],
            input_artifacts=["/etc/passwd"]
        )

    with pytest.raises(ValidationError):
        ExperimentExecutionSpec(
            experiment_id="exp1",
            variant_id="var1",
            runner_type="local",
            workload="python",
            entrypoint=["python", "script.py"],
            output_artifacts=["../secrets.txt"]
        )

    # Valid artifact paths
    spec2 = ExperimentExecutionSpec(
        experiment_id="exp1",
        variant_id="var1",
        runner_type="local",
        workload="python",
        entrypoint=["python", "script.py"],
        input_artifacts=["dataset.csv"],
        output_artifacts=["results.json"]
    )
    assert spec2.input_artifacts == ["dataset.csv"]

@pytest.mark.asyncio
async def test_local_isolated_runner_security_boundary():
    from app.services.runner import LocalIsolatedRunner, ExecutionFailure
    from unittest.mock import AsyncMock
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.models import ExperimentRun

    session = AsyncMock(spec=AsyncSession)
    run = ExperimentRun(id="run123")
    runner = LocalIsolatedRunner()

    spec = ExperimentExecutionSpec(
        experiment_id="exp1",
        variant_id="var1",
        runner_type="local",
        workload="python",
        entrypoint=["python", "script.py"],
        environment={"BAD/VAR": "value"}
    )

    # Should catch validation error in runner for environment variables
    # Since we can't test Docker easily in unit tests without docker running,
    # we just test the security boundaries enforced before Docker is called.
    result = await runner.execute(session, run, spec)
    assert result.success is False
    assert "VALIDATION_ERROR" in result.error_info
