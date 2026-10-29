"""
AEROWIND — Task-Aware Model Router
====================================
Selects the best available provider and model based on:
1. Task type (reasoning, code generation, classification, etc.)
2. Provider health
3. Explicit overrides in the request
4. Cost preferences
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.gateway import GatewayRequest, Provider, TaskType

logger = get_logger(__name__)

# Task → preferred provider ordering
_TASK_PROVIDER_PREFERENCE: dict[TaskType, list[Provider]] = {
    # Heavy reasoning tasks → Nemotron first
    TaskType.REASONING: [Provider.NEBIUS, Provider.OPENAI, Provider.ANTHROPIC, Provider.GEMINI],
    TaskType.HYPOTHESIS_GENERATION: [Provider.NEBIUS, Provider.ANTHROPIC, Provider.OPENAI, Provider.GEMINI],
    TaskType.EXPERIMENT_DESIGN: [Provider.NEBIUS, Provider.ANTHROPIC, Provider.OPENAI, Provider.GEMINI],
    # Code generation → Nemotron / Claude
    TaskType.CODE_GENERATION: [Provider.NEBIUS, Provider.ANTHROPIC, Provider.OPENAI, Provider.GEMINI],
    # Analysis tasks
    TaskType.ANALYSIS: [Provider.NEBIUS, Provider.ANTHROPIC, Provider.OPENAI, Provider.GEMINI],
    # Report generation → long context preferred
    TaskType.REPORT_GENERATION: [Provider.NEBIUS, Provider.ANTHROPIC, Provider.OPENAI, Provider.GEMINI],
    # Fast/cheap tasks → fast model preferred
    TaskType.CLASSIFICATION: [Provider.NEBIUS, Provider.GEMINI, Provider.OPENAI, Provider.ANTHROPIC],
    # General fallback
    TaskType.GENERAL: [Provider.NEBIUS, Provider.OPENAI, Provider.ANTHROPIC, Provider.GEMINI],
}

# Task → model override within a provider
_NEBIUS_TASK_MODEL: dict[TaskType, str] = {
    TaskType.REASONING: settings.NEBIUS_REASONING_MODEL,
    TaskType.HYPOTHESIS_GENERATION: settings.NEBIUS_REASONING_MODEL,
    TaskType.EXPERIMENT_DESIGN: settings.NEBIUS_REASONING_MODEL,
    TaskType.CODE_GENERATION: settings.NEBIUS_REASONING_MODEL,
    TaskType.ANALYSIS: settings.NEBIUS_REASONING_MODEL,
    TaskType.REPORT_GENERATION: settings.NEBIUS_REASONING_MODEL,
    TaskType.CLASSIFICATION: settings.NEBIUS_FAST_MODEL,
    TaskType.GENERAL: settings.NEBIUS_DEFAULT_MODEL,
}


class ModelRouter:
    """
    Selects the optimal provider and model for a given GatewayRequest.
    Does NOT make any network calls — that is the gateway's job.
    """

    def __init__(self, healthy_providers: set[Provider]) -> None:
        self._healthy = healthy_providers

    def route(self, request: GatewayRequest) -> tuple[Provider, str | None]:
        """
        Return (provider, model_override_or_None) for this request.

        If request has explicit preferred_provider + preferred_model, respect them.
        Otherwise use task-type routing.
        """
        # Explicit override wins
        if request.preferred_provider:
            provider = request.preferred_provider
            model = request.preferred_model or self._default_model_for(
                provider, request.task_type
            )
            logger.debug(
                "router.explicit_override",
                provider=provider,
                model=model,
                task=request.task_type,
            )
            return provider, model

        # Task-aware routing
        preference = _TASK_PROVIDER_PREFERENCE.get(
            request.task_type, _TASK_PROVIDER_PREFERENCE[TaskType.GENERAL]
        )

        for candidate in preference:
            if candidate in self._healthy:
                model = self._default_model_for(candidate, request.task_type)
                logger.debug(
                    "router.selected",
                    provider=candidate,
                    model=model,
                    task=request.task_type,
                )
                return candidate, model

        # No healthy provider found — caller handles this
        logger.warning("router.no_healthy_provider", task=request.task_type)
        raise RuntimeError("No healthy providers available for routing")

    @staticmethod
    def _default_model_for(provider: Provider, task_type: TaskType) -> str | None:
        """Return the recommended model for provider + task_type, or None to use adapter default."""
        if provider == Provider.NEBIUS:
            return _NEBIUS_TASK_MODEL.get(task_type, settings.NEBIUS_DEFAULT_MODEL)
        # Other providers use their adapter-configured defaults
        return None
