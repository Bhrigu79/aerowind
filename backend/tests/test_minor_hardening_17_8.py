import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from app.main import app
from app.core.exceptions import GatewayError
from app.services.ai_benchmark import RealAIBenchmarkRunner
from app.db.models import ExperimentRun, ExperimentVariant
import os
import json

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_api_does_not_expose_raw_error_body(client):
    # Mock gateway complete to raise an exception containing a sensitive body
    sensitive_error_message = "Nebius API error 400: sensitive raw body with internal details"

    with patch("app.api.v1.providers._get_gw") as mock_get_gw:
        mock_gateway = MagicMock()
        mock_gateway.complete = AsyncMock(side_effect=GatewayError(sensitive_error_message))
        mock_get_gw.return_value = mock_gateway

        req_payload = {
            "task_type": "general",
            "messages": [{"role": "user", "content": "hello"}]
        }

        response = client.post("/api/v1/gateway/complete", json=req_payload)

        assert response.status_code == 502
        data = response.json()
        assert "External model provider request failed." in data["detail"]
        assert "sensitive raw body" not in data["detail"]
        assert "Nebius API error" not in data["detail"]

def test_ai_api_does_not_expose_raw_error_body(client):
    sensitive_error_message = "Nebius API error 400: secret_key=123"

    with patch("app.api.v1.ai._get_gw") as mock_get_gw:
        mock_gateway = MagicMock()
        mock_gateway.complete = AsyncMock(side_effect=Exception(sensitive_error_message))
        mock_get_gw.return_value = mock_gateway

        req_payload = {
            "prompt": "test"
        }

        response = client.post("/api/v1/ai/test", json=req_payload)

        assert response.status_code == 502
        data = response.json()
        assert "External model provider request failed." in data["detail"]
        assert "secret_key=123" not in data["detail"]

@pytest.mark.asyncio
async def test_runner_fails_if_model_missing():
    runner = RealAIBenchmarkRunner(gateway=MagicMock())

    mock_session = AsyncMock()
    variant = ExperimentVariant(
        system_configuration={"temperature": 0.5}  # Missing "model"
    )
    mock_session.get.return_value = variant

    run = ExperimentRun(variant_id="mock_id")

    import pytest
    with pytest.raises(ValueError, match="RealAIBenchmarkRunner requires an explicit 'model' in the configuration."):
        await runner.execute(mock_session, run)

@pytest.mark.asyncio
async def test_runner_succeeds_with_model():
    runner = RealAIBenchmarkRunner(gateway=MagicMock())
    runner.gateway.complete = AsyncMock()
    runner.dataset = runner.dataset[:1]  # minimal

    mock_session = AsyncMock()
    variant = ExperimentVariant(
        project_id="p1",
        system_configuration={"temperature": 0.5, "model": "nvidia/llama-3.1-nemotron-70b-instruct"}
    )
    mock_session.get.return_value = variant

    run = ExperimentRun(id="run1", variant_id="mock_id", experiment_id="e1")

    # Should not raise ValueError for missing model
    try:
        await runner.execute(mock_session, run)
    except Exception as e:
        if isinstance(e, ValueError) and "explicit 'model'" in str(e):
            pytest.fail("Raised ValueError for missing model even though it was provided")
