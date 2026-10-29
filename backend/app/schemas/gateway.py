"""
AEROWIND Pydantic Schemas — Model Gateway
==========================================
All data structures that flow through the Model Gateway.
These schemas are provider-agnostic by design.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Types of tasks agents can request — used for intelligent routing."""

    # Heavy reasoning tasks → routes to Nemotron / strongest available model
    REASONING = "reasoning"
    # Hypothesis generation for experiments
    HYPOTHESIS_GENERATION = "hypothesis_generation"
    # Experiment design and planning
    EXPERIMENT_DESIGN = "experiment_design"
    # Code generation / modification
    CODE_GENERATION = "code_generation"
    # Result analysis and interpretation
    ANALYSIS = "analysis"
    # Report generation
    REPORT_GENERATION = "report_generation"
    # Quick classification or extraction
    CLASSIFICATION = "classification"
    # General / fallback
    GENERAL = "general"


class Provider(str, Enum):
    """Supported model providers."""

    NEBIUS = "nebius"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """A single message in a conversation."""

    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None


class GatewayRequest(BaseModel):
    """
    The unified request object that agents pass to the ModelGateway.
    Agents NEVER construct provider-specific requests directly.
    """

    # What the agent wants to accomplish (used for routing)
    task_type: TaskType = TaskType.GENERAL

    # Conversation messages
    messages: list[Message]

    # Optional: override provider / model selection
    preferred_provider: Provider | None = None
    preferred_model: str | None = None
    allow_fallback: bool = True

    # Generation parameters
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0
    stream: bool = False

    # Identification (for usage tracking)
    project_id: str | None = None
    experiment_id: str | None = None
    agent_id: str | None = None

    # Extra provider-specific kwargs (use sparingly)
    extra: dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    """Token usage breakdown from a provider response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    is_missing: bool = False
    known_cost_usd: float | None = None

    @property
    def estimated_cost_usd(self) -> float | None:
        """
        Rough cost estimate in USD.
        Returns None if usage was missing or explicitly unknown.
        """
        if self.is_missing:
            return None
        if self.known_cost_usd is not None:
            return self.known_cost_usd
        if self.total_tokens == 0:
            return None
        # Conservative estimate at ~$0.50/1M tokens blended
        return (self.total_tokens / 1_000_000) * 0.50


class GatewayResponse(BaseModel):
    """
    The unified response object returned by the ModelGateway.
    Agents NEVER see provider-specific response objects.
    """

    # The generated content
    content: str

    # Which provider/model actually served this request
    provider: Provider
    model: str

    # Usage data
    usage: TokenUsage

    # Timing
    latency_ms: float  # wall-clock milliseconds for this call

    # Metadata
    request_id: str
    finish_reason: Literal["stop", "length", "tool_calls", "error"] = "stop"

    # Was this served from a fallback provider?
    was_fallback: bool = False
    fallback_from: Provider | None = None


class ProviderHealth(BaseModel):
    """Health status for a single provider."""

    provider: Provider
    is_healthy: bool
    last_checked_at: str  # ISO timestamp
    consecutive_failures: int = 0
    avg_latency_ms: float | None = None
    error_rate: float = 0.0  # 0.0–1.0
    message: str | None = None


class GatewayStatus(BaseModel):
    """Overall gateway status — exposed via /health endpoint."""

    default_provider: Provider
    providers: list[ProviderHealth]
    total_requests: int
    total_tokens: int
    estimated_cost_usd: float
