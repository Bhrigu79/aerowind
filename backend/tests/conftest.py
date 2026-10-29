"""
pytest configuration and fixtures for AEROWIND tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    """Create a test client for the FastAPI app."""
    # Override env for tests
    import os
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://aerowind:aerowind@localhost:5432/aerowind")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("NEBIUS_ENABLED", "false")  # Don't hit real APIs in tests
    os.environ.setdefault("OPENAI_ENABLED", "false")
    os.environ.setdefault("ANTHROPIC_ENABLED", "false")
    os.environ.setdefault("GEMINI_ENABLED", "false")

    from app.main import app
    with TestClient(app) as c:
        yield c
