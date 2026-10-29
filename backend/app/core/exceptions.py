"""
AEROWIND Exception Hierarchy
==============================
All application-specific exceptions are defined here.
HTTP mapping is done at the API layer — never raise HTTPException from business logic.
"""

from __future__ import annotations


class AerowindError(Exception):
    """Base exception for all AEROWIND errors."""

    def __init__(self, message: str, code: str = "AEROWIND_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# ── Gateway Errors ────────────────────────────────────────────────────────────

class GatewayError(AerowindError):
    """Base class for Model Gateway errors."""


class ProviderUnavailableError(GatewayError):
    """Raised when a provider is unhealthy or unreachable."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Provider '{provider}' is unavailable.",
            code="PROVIDER_UNAVAILABLE",
        )
        self.provider = provider


class NoProvidersAvailableError(GatewayError):
    """Raised when no providers are healthy and available."""

    def __init__(self) -> None:
        super().__init__(
            "No model providers are currently available.",
            code="NO_PROVIDERS_AVAILABLE",
        )


class RateLimitError(GatewayError):
    """Raised when a provider rate limit is hit."""

    def __init__(self, provider: str, retry_after: float | None = None) -> None:
        super().__init__(
            f"Rate limit hit for provider '{provider}'.",
            code="RATE_LIMIT",
        )
        self.provider = provider
        self.retry_after = retry_after


class QuotaExceededError(GatewayError):
    """Raised when a provider quota is exceeded."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"Quota exceeded for provider '{provider}'.",
            code="QUOTA_EXCEEDED",
        )
        self.provider = provider


class ModelNotFoundError(GatewayError):
    """Raised when the requested model does not exist on the provider."""

    def __init__(self, model: str, provider: str) -> None:
        super().__init__(
            f"Model '{model}' not found on provider '{provider}'.",
            code="MODEL_NOT_FOUND",
        )
        self.model = model
        self.provider = provider


class GatewayTimeoutError(GatewayError):
    """Raised when a provider call times out."""

    def __init__(self, provider: str, timeout: float) -> None:
        super().__init__(
            f"Request to provider '{provider}' timed out after {timeout}s.",
            code="GATEWAY_TIMEOUT",
        )
        self.provider = provider
        self.timeout = timeout


# ── Project / Experiment Errors ───────────────────────────────────────────────

class ProjectNotFoundError(AerowindError):
    def __init__(self, project_id: str) -> None:
        super().__init__(f"Project '{project_id}' not found.", code="PROJECT_NOT_FOUND")
        self.project_id = project_id


class ExperimentNotFoundError(AerowindError):
    def __init__(self, experiment_id: str) -> None:
        super().__init__(
            f"Experiment '{experiment_id}' not found.",
            code="EXPERIMENT_NOT_FOUND",
        )
        self.experiment_id = experiment_id


class HypothesisNotFoundError(AerowindError):
    def __init__(self, hypothesis_id: str) -> None:
        super().__init__(
            f"Hypothesis '{hypothesis_id}' not found.",
            code="HYPOTHESIS_NOT_FOUND",
        )
        self.hypothesis_id = hypothesis_id


class ExperimentStateError(AerowindError):
    """Raised on invalid experiment state transitions."""

    def __init__(self, current: str, attempted: str) -> None:
        super().__init__(
            f"Cannot transition experiment from '{current}' to '{attempted}'.",
            code="EXPERIMENT_STATE_ERROR",
        )


# ── Sandbox Errors ────────────────────────────────────────────────────────────

class SandboxError(AerowindError):
    """Base class for sandbox execution errors."""


class SandboxTimeoutError(SandboxError):
    def __init__(self, timeout: int) -> None:
        super().__init__(
            f"Sandbox execution timed out after {timeout}s.",
            code="SANDBOX_TIMEOUT",
        )


class SandboxExecutionError(SandboxError):
    def __init__(self, exit_code: int, stderr: str) -> None:
        super().__init__(
            f"Sandbox exited with code {exit_code}: {stderr[:200]}",
            code="SANDBOX_EXECUTION_ERROR",
        )
        self.exit_code = exit_code
        self.stderr = stderr
