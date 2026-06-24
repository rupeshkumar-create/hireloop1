"""
Tests for the /api/v1/health endpoint.
These run in CI without a real database — they test the API process only.
"""

import pytest
from fastapi.testclient import TestClient

from hireloop_api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_response_body(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "hireloop-api"
    assert "environment" in data
    assert "uptime_seconds" in data
    assert "timestamp" in data


def test_health_content_type(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert "application/json" in response.headers["content-type"]


def test_unknown_route_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
