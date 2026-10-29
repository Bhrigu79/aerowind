"""
AEROWIND API Tests
===================
Integration tests for the FastAPI routes.
Uses TestClient with in-memory stores.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=True)


class TestHealthEndpoints:
    def test_root(self) -> None:
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "AEROWIND"

    def test_health(self) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data


class TestProjectsAPI:
    def test_create_project(self) -> None:
        response = client.post(
            "/api/v1/projects/",
            json={
                "name": "Test Project",
                "objective": "Improve quality above 92% while keeping P95 latency below 2000ms",
                "constraints": [
                    {
                        "metric": "quality_score",
                        "operator": ">=",
                        "value": 92.0,
                        "unit": "percent",
                    },
                    {
                        "metric": "p95_latency_ms",
                        "operator": "<=",
                        "value": 2000.0,
                        "unit": "ms",
                    },
                ],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["status"] == "draft"
        assert len(data["constraints"]) == 2
        return data["id"]

    def test_list_projects(self) -> None:
        response = client.get("/api/v1/projects/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_project_not_found(self) -> None:
        response = client.get("/api/v1/projects/nonexistent-id")
        assert response.status_code == 404

    def test_full_project_lifecycle(self) -> None:
        # Create
        create_resp = client.post(
            "/api/v1/projects/",
            json={
                "name": "Lifecycle Test",
                "objective": "Test the full project lifecycle",
            },
        )
        assert create_resp.status_code == 201
        project_id = create_resp.json()["id"]

        # Get
        get_resp = client.get(f"/api/v1/projects/{project_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == project_id

        # Update
        update_resp = client.patch(
            f"/api/v1/projects/{project_id}",
            json={"status": "active"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == "active"

        # Delete
        delete_resp = client.delete(f"/api/v1/projects/{project_id}")
        assert delete_resp.status_code == 204

        # Confirm deleted
        confirm_resp = client.get(f"/api/v1/projects/{project_id}")
        assert confirm_resp.status_code == 404


class TestExperimentsAPI:
    def _create_project(self) -> str:
        resp = client.post(
            "/api/v1/projects/",
            json={"name": "Exp Test Project", "objective": "Test experiment API"},
        )
        return resp.json()["id"]

    def test_create_experiment(self) -> None:
        project_id = self._create_project()
        response = client.post(
            "/api/v1/experiments/",
            json={
                "project_id": project_id,
                "name": "Prompt Optimization #1",
                "experiment_type": "prompt_optimization",
                "candidate_description": "Replace verbose system prompt with concise version",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"
        assert data["sequence_number"] == 1

    def test_list_experiments_by_project(self) -> None:
        project_id = self._create_project()
        client.post(
            "/api/v1/experiments/",
            json={
                "project_id": project_id,
                "name": "Exp A",
                "experiment_type": "model_swap",
                "candidate_description": "Swap to Nemotron 70B",
            },
        )
        response = client.get(f"/api/v1/experiments/?project_id={project_id}")
        assert response.status_code == 200
        experiments = response.json()
        assert len(experiments) >= 1

    def test_experiment_not_found(self) -> None:
        response = client.get("/api/v1/experiments/does-not-exist")
        assert response.status_code == 404

    def test_start_experiment(self) -> None:
        project_id = self._create_project()
        create_resp = client.post(
            "/api/v1/experiments/",
            json={
                "project_id": project_id,
                "name": "Start Test",
                "experiment_type": "config_tuning",
                "candidate_description": "Lower temperature to 0.3",
            },
        )
        exp_id = create_resp.json()["id"]
        start_resp = client.post(f"/api/v1/experiments/{exp_id}/start")
        assert start_resp.status_code == 200
        assert start_resp.json()["status"] == "running"

    def test_cannot_start_running_experiment(self) -> None:
        project_id = self._create_project()
        create_resp = client.post(
            "/api/v1/experiments/",
            json={
                "project_id": project_id,
                "name": "Double Start Test",
                "experiment_type": "config_tuning",
                "candidate_description": "test",
            },
        )
        exp_id = create_resp.json()["id"]
        client.post(f"/api/v1/experiments/{exp_id}/start")
        second_start = client.post(f"/api/v1/experiments/{exp_id}/start")
        assert second_start.status_code == 409


class TestHypothesesAPI:
    def _create_project(self) -> str:
        resp = client.post(
            "/api/v1/projects/",
            json={"name": "Hyp Test Project", "objective": "Test hypotheses API"},
        )
        return resp.json()["id"]

    def test_create_hypothesis(self) -> None:
        project_id = self._create_project()
        response = client.post(
            "/api/v1/hypotheses/",
            json={
                "project_id": project_id,
                "statement": "Using parallel model calls will reduce P95 latency by 40%",
                "rationale": "Sequential calls accumulate latency; parallel execution should reduce it",
                "priority": 80,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"
        assert data["priority"] == 80

    def test_list_hypotheses_sorted_by_priority(self) -> None:
        project_id = self._create_project()
        for priority in [10, 90, 50]:
            client.post(
                "/api/v1/hypotheses/",
                json={
                    "project_id": project_id,
                    "statement": f"Hypothesis at priority {priority}",
                    "priority": priority,
                },
            )
        response = client.get(f"/api/v1/hypotheses/?project_id={project_id}")
        assert response.status_code == 200
        hypotheses = response.json()
        priorities = [h["priority"] for h in hypotheses]
        assert priorities == sorted(priorities, reverse=True)
