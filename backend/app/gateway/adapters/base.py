"""
AEROWIND Model Gateway — Base Provider Adapter
===============================================
All provider adapters MUST implement this interface.
Agents never import these adapters directly.
"""

from __future__ import annotations

import abc
import time
from typing import AsyncIterator

from app.schemas.gateway import GatewayRequest, GatewayResponse, ProviderHealth


class BaseProviderAdapter(abc.ABC):
    """
    Abstract base class for all model provider adapters.

    Contract:
    - Adapters convert GatewayRequest → provider API call → GatewayResponse
    - Adapters MUST NOT leak provider-specific types to callers
    - Adapters MUST report accurate latency and token usage
    - Adapters MUST raise appropriate AerowindError subclasses (not HTTP errors)
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Return the canonical provider name (e.g. 'nebius', 'openai')."""
        ...

    @property
    @abc.abstractmethod
    def is_enabled(self) -> bool:
        """Return True if this provider is configured and enabled."""
        ...

    @abc.abstractmethod
    async def complete(self, request: GatewayRequest) -> GatewayResponse:
        """
        Execute a completion request against this provider.

        Args:
            request: Provider-agnostic GatewayRequest

        Returns:
            Provider-agnostic GatewayResponse

        Raises:
            ProviderUnavailableError: If the provider endpoint is unreachable
            RateLimitError: If the provider returns 429
            QuotaExceededError: If quota/billing is exhausted
            GatewayTimeoutError: If the request times out
            ModelNotFoundError: If the requested model doesn't exist
            GatewayError: For any other provider-level error
        """
        ...

    @abc.abstractmethod
    async def stream(self, request: GatewayRequest) -> AsyncIterator[str]:
        """
        Stream completion tokens from this provider.

        Yields:
            Token strings as they arrive

        Raises:
            Same exceptions as complete()
        """
        ...

    @abc.abstractmethod
    async def health_check(self) -> ProviderHealth:
        """
        Perform a lightweight health check against this provider.

        Returns:
            ProviderHealth describing current status
        """
        ...

    @staticmethod
    def _now_ms() -> float:
        """Return current time in milliseconds."""
        return time.monotonic() * 1000
