"""
AEROWIND Core Configuration
============================
All settings are loaded from environment variables / .env file.
Never import provider SDKs here — this is pure configuration.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Application-level settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_DEBUG: bool = True
    SECRET_KEY: str = "changeme"

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///aerowind.db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── Model Gateway ─────────────────────────────────────────────────────────
    MODEL_GATEWAY_DEFAULT_PROVIDER: str = "nebius"
    MODEL_GATEWAY_TIMEOUT: int = 60
    MODEL_GATEWAY_MAX_RETRIES: int = 3
    MODEL_GATEWAY_RETRY_DELAY: float = 1.0

    # ── Nebius / NVIDIA ───────────────────────────────────────────────────────
    NEBIUS_API_KEY: str = ""
    NEBIUS_BASE_URL: str = "https://api.studio.nebius.ai/v1"
    NEBIUS_DEFAULT_MODEL: str = "nvidia/llama-3.1-nemotron-70b-instruct"
    NEBIUS_REASONING_MODEL: str = "nvidia/llama-3.1-nemotron-70b-instruct"
    NEBIUS_FAST_MODEL: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"
    NEBIUS_ENABLED: bool = True

    # ── OpenAI ────────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_DEFAULT_MODEL: str = "gpt-4o-mini"
    OPENAI_ENABLED: bool = False

    # ── Anthropic ─────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_DEFAULT_MODEL: str = "claude-3-5-haiku-latest"
    ANTHROPIC_ENABLED: bool = False

    # ── Gemini ────────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GEMINI_DEFAULT_MODEL: str = "gemini-1.5-flash"
    GEMINI_ENABLED: bool = False

    # ── Object Storage ────────────────────────────────────────────────────────
    STORAGE_ENDPOINT: str = ""
    STORAGE_ACCESS_KEY: str = ""
    STORAGE_SECRET_KEY: str = ""
    STORAGE_BUCKET: str = "aerowind-artifacts"
    STORAGE_REGION: str = "eu-north1"

    # ── Sandbox ───────────────────────────────────────────────────────────────
    SANDBOX_DOCKER_IMAGE: str = "python:3.11-slim"
    SANDBOX_TIMEOUT: int = 300
    SANDBOX_MEMORY_LIMIT: str = "512m"
    SANDBOX_CPU_QUOTA: int = 100000

    # ── Observability ─────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "json"
    METRICS_ENABLED: bool = True
    METRICS_PORT: int = 9090

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        return v

    # ── Nebius Execution (Serverless Jobs) ───────────────────────────────────
    NEBIUS_EXEC_ENABLED: bool = False
    NEBIUS_EXEC_PROJECT_ID: str = ""
    NEBIUS_EXEC_SERVICE_ACCOUNT_ID: str = ""
    NEBIUS_EXEC_PUBLIC_KEY_ID: str = ""
    NEBIUS_EXEC_PRIVATE_KEY_FILE: str = ""
    NEBIUS_EXEC_DEFAULT_GPU_PLATFORM: str = "gpu-h100-sxm"
    NEBIUS_EXEC_DEFAULT_PRESET: str = "1gpu-16vcpu-200gb"
    NEBIUS_EXEC_DEFAULT_TIMEOUT_SECONDS: int = 3600
    NEBIUS_EXEC_CONTAINER_REGISTRY: str = "cr.eu-north1.nebius.cloud/my-registry"
    NEBIUS_EXEC_S3_BUCKET: str = ""
    NEBIUS_EXEC_S3_ACCESS_KEY: str = ""
    NEBIUS_EXEC_S3_SECRET_KEY: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def enabled_providers(self) -> list[str]:
        providers = []
        if self.NEBIUS_ENABLED and self.NEBIUS_API_KEY:
            providers.append("nebius")
        if self.OPENAI_ENABLED and self.OPENAI_API_KEY:
            providers.append("openai")
        if self.ANTHROPIC_ENABLED and self.ANTHROPIC_API_KEY:
            providers.append("anthropic")
        if self.GEMINI_ENABLED and self.GEMINI_API_KEY:
            providers.append("gemini")
        return providers


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached application settings singleton."""
    return AppSettings()


# Convenience alias
settings = get_settings()
