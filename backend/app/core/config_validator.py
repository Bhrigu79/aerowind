"""
AEROWIND — Candidate Configuration Validator
=============================================

This module is the single authoritative boundary between a proposed
configuration (from the LLM) and an executed experiment.

INVARIANT:
    proposed_config
        → validated (or rejected with explicit reason)
        → actually executed
        → measured metrics
        → deterministic decision

There must NEVER be a case where the runner silently executes a
different configuration from the one proposed.

Supported search-space dimensions are defined canonically here.
The strategy engine, the runner, and this validator share these definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Canonical supported values for enum-like dimensions
# These are the ONLY values that have a defined measurable effect in
# SyntheticExperimentRunner.  Any other value is rejected.
# ---------------------------------------------------------------------------

SUPPORTED_PROMPT_STRATEGIES: frozenset[str] = frozenset({"direct", "structured"})

SUPPORTED_PIPELINE_MODES: frozenset[str] = frozenset({"single", "draft_critique"})

# Model names recognised by SyntheticExperimentRunner substring matching.
# We normalise to these canonical identifiers.
SUPPORTED_MODELS: frozenset[str] = frozenset({
    "default",
    "nemotron-70b",      # "70b" substring → large model branch
    "nemotron-8b",       # "8b"  substring → small model branch
    "llama-70b",
    "llama-8b",
    "qwen-72b",
    "qwen-7b",
    "large",             # generic large — kept for backwards compat
    "small",             # generic small — kept for backwards compat
})

# Numeric bounds
TEMPERATURE_MIN: float = 0.0
TEMPERATURE_MAX: float = 2.0

MAX_TOKENS_MIN: int = 1
MAX_TOKENS_MAX: int = 32768

FEW_SHOT_COUNT_MIN: int = 0
FEW_SHOT_COUNT_MAX: int = 20

# All dimensions known to the search space
KNOWN_DIMENSIONS: frozenset[str] = frozenset({
    "temperature",
    "max_tokens",
    "few_shot_count",
    "retrieval_enabled",
    "chain_of_thought",
    "model",
    "prompt_strategy",
    "pipeline_mode",
})


# ---------------------------------------------------------------------------
# Result object
# ---------------------------------------------------------------------------

@dataclass
class ConfigValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)

    @property
    def error_message(self) -> str:
        return "; ".join(self.errors)

    @classmethod
    def ok(cls) -> "ConfigValidationResult":
        return cls(valid=True)

    @classmethod
    def fail(cls, *errors: str) -> "ConfigValidationResult":
        return cls(valid=False, errors=list(errors))


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class ConfigurationValidator:
    """
    Validates a candidate_configuration dict against the AEROWIND search space.

    Rules:
      - Only known dimensions are permitted (unknown keys are rejected).
      - Each dimension is validated for type and allowed values.
      - No coercion, no defaulting — wrong type → rejected.
    """

    @staticmethod
    def validate(config: Dict[str, Any]) -> ConfigValidationResult:
        if not isinstance(config, dict):
            return ConfigValidationResult.fail("candidate_configuration must be a dict")

        errors: List[str] = []

        # Check for unknown dimensions
        unknown = set(config.keys()) - KNOWN_DIMENSIONS
        if unknown:
            errors.append(
                f"Unknown configuration dimensions: {sorted(unknown)}. "
                f"Supported: {sorted(KNOWN_DIMENSIONS)}"
            )

        # --- temperature ---
        if "temperature" in config:
            v = config["temperature"]
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                errors.append(
                    f"temperature must be a float; got {type(v).__name__!r} value={v!r}"
                )
            else:
                v = float(v)
                if not (TEMPERATURE_MIN <= v <= TEMPERATURE_MAX):
                    errors.append(
                        f"temperature must be in [{TEMPERATURE_MIN}, {TEMPERATURE_MAX}]; got {v}"
                    )

        # --- max_tokens ---
        if "max_tokens" in config:
            v = config["max_tokens"]
            if not isinstance(v, int) or isinstance(v, bool):
                errors.append(
                    f"max_tokens must be an integer; got {type(v).__name__!r} value={v!r}"
                )
            else:
                if not (MAX_TOKENS_MIN <= v <= MAX_TOKENS_MAX):
                    errors.append(
                        f"max_tokens must be in [{MAX_TOKENS_MIN}, {MAX_TOKENS_MAX}]; got {v}"
                    )

        # --- few_shot_count ---
        if "few_shot_count" in config:
            v = config["few_shot_count"]
            if not isinstance(v, int) or isinstance(v, bool):
                errors.append(
                    f"few_shot_count must be an integer; got {type(v).__name__!r} value={v!r}"
                )
            else:
                if not (FEW_SHOT_COUNT_MIN <= v <= FEW_SHOT_COUNT_MAX):
                    errors.append(
                        f"few_shot_count must be in [{FEW_SHOT_COUNT_MIN}, {FEW_SHOT_COUNT_MAX}]; got {v}"
                    )

        # --- retrieval_enabled ---
        if "retrieval_enabled" in config:
            v = config["retrieval_enabled"]
            if not isinstance(v, bool):
                errors.append(
                    f"retrieval_enabled must be a boolean; got {type(v).__name__!r} value={v!r}"
                )

        # --- chain_of_thought ---
        if "chain_of_thought" in config:
            v = config["chain_of_thought"]
            if not isinstance(v, bool):
                errors.append(
                    f"chain_of_thought must be a boolean; got {type(v).__name__!r} value={v!r}"
                )

        # --- model ---
        if "model" in config:
            v = config["model"]
            if not isinstance(v, str):
                errors.append(
                    f"model must be a string; got {type(v).__name__!r} value={v!r}"
                )
            elif v not in SUPPORTED_MODELS:
                errors.append(
                    f"model {v!r} is not a recognised value. "
                    f"Supported: {sorted(SUPPORTED_MODELS)}"
                )

        # --- prompt_strategy ---
        if "prompt_strategy" in config:
            v = config["prompt_strategy"]
            if not isinstance(v, str):
                errors.append(
                    f"prompt_strategy must be a string; got {type(v).__name__!r} value={v!r}"
                )
            elif v not in SUPPORTED_PROMPT_STRATEGIES:
                errors.append(
                    f"prompt_strategy {v!r} is not a recognised value. "
                    f"Supported: {sorted(SUPPORTED_PROMPT_STRATEGIES)}"
                )

        # --- pipeline_mode ---
        if "pipeline_mode" in config:
            v = config["pipeline_mode"]
            if not isinstance(v, str):
                errors.append(
                    f"pipeline_mode must be a string; got {type(v).__name__!r} value={v!r}"
                )
            elif v not in SUPPORTED_PIPELINE_MODES:
                errors.append(
                    f"pipeline_mode {v!r} is not a recognised value. "
                    f"Supported: {sorted(SUPPORTED_PIPELINE_MODES)}"
                )

        if errors:
            return ConfigValidationResult(valid=False, errors=errors)
        return ConfigValidationResult.ok()

    @staticmethod
    def normalize(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a canonical representation of the configuration by filling
        in known implicit defaults. This enables reliable structural equality checks.
        """
        defaults = {
            "temperature": 0.7,
            "max_tokens": 1024,
            "few_shot_count": 0,
            "retrieval_enabled": False,
            "chain_of_thought": False,
            "model": "default",
            "prompt_strategy": "direct",
            "pipeline_mode": "single"
        }

        normalized = {}
        for dim in sorted(KNOWN_DIMENSIONS):
            if dim in config and config[dim] is not None:
                normalized[dim] = config[dim]
            else:
                normalized[dim] = defaults.get(dim)

        return normalized

    @staticmethod
    def diff_effective_config(baseline_config: Dict[str, Any], candidate_config: Dict[str, Any]) -> List[str]:
        """
        Deterministically compares two configurations after applying implicit defaults.
        Returns a sorted list of dimensions that effectively changed.
        """
        norm_base = ConfigurationValidator.normalize(baseline_config)
        norm_cand = ConfigurationValidator.normalize(candidate_config)

        changed = []
        for dim in sorted(KNOWN_DIMENSIONS):
            if norm_base.get(dim) != norm_cand.get(dim):
                changed.append(dim)

        return changed
