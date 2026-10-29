from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional

class ResourceLimits(BaseModel):
    timeout_seconds: int = Field(default=300, le=3600)
    cpu_cores: float = Field(default=1.0, le=8.0)
    memory_mb: int = Field(default=512, le=8192)
    gpu_required: bool = False
    max_output_bytes: int = Field(default=1024 * 1024 * 10)  # 10 MB limit

class ExperimentExecutionSpec(BaseModel):
    experiment_id: str
    variant_id: str
    runner_type: str
    workload: str
    entrypoint: List[str]
    environment: Dict[str, str] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    input_artifacts: List[str] = Field(default_factory=list)
    output_artifacts: List[str] = Field(default_factory=list)
    measurement_configuration: Dict[str, str] = Field(default_factory=dict)

    @field_validator("entrypoint")
    @classmethod
    def validate_entrypoint(cls, v):
        if not v:
            raise ValueError("Entrypoint must not be empty")
        # Reject shell builtins or arbitrary bash concatenations
        forbidden = ["sh", "bash", "&&", ";", "|", ">", "<"]
        for cmd in v:
            if any(f in cmd for f in forbidden):
                raise ValueError(f"Forbidden command or character in entrypoint: {cmd}")
        return v

    @field_validator("input_artifacts", "output_artifacts")
    @classmethod
    def validate_artifact_paths(cls, v):
        for path in v:
            if ".." in path or path.startswith("/"):
                raise ValueError(f"Artifact paths must be relative and cannot traverse up: {path}")
        return v
