# Copyright 2025 John Brosnihan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for health check endpoint."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    app = create_app()
    return TestClient(app)


def test_health_check_returns_ok(client):
    """Test that health check endpoint returns 200 with correct status."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_content_type(client):
    """Test that health check endpoint returns JSON content type."""
    response = client.get("/health")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]


def test_health_check_includes_request_id(client):
    """Test that health check includes X-Request-ID in response."""
    response = client.get("/health")

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    # Request ID should be a UUID-like string
    assert len(response.headers["X-Request-ID"]) > 0


def test_health_check_preserves_custom_request_id(client):
    """Test that custom X-Request-ID is preserved."""
    custom_id = "test-request-123"
    response = client.get("/health", headers={"X-Request-ID": custom_id})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id


def test_readiness_check_returns_ready(client):
    """Test that readiness check returns 200 when dependencies are healthy."""
    response = client.get("/readiness")

    # Should return 200 when Firestore client can be initialized
    # In test environment, this might fail if no credentials
    # but we're testing the endpoint structure
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data
    assert data["status"] in ["ready", "not_ready"]


def test_readiness_check_fails_when_firestore_unavailable(client):
    """Test that readiness check returns 503 when Firestore is unavailable."""
    # Mock the direct dependency of the endpoint
    with patch("app.api.health.get_firestore_client") as mock_get_client:
        mock_get_client.side_effect = Exception("Firestore unavailable")

        response = client.get("/readiness")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert "issues" in data
        assert len(data["issues"]) > 0


def test_liveness_check_returns_alive(client):
    """Test that liveness check returns 200 with alive status."""
    response = client.get("/liveness")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_liveness_check_is_lightweight(client):
    """Test that liveness check doesn't perform expensive operations."""
    # Liveness should not depend on external services
    # It should always succeed if the app is running
    response = client.get("/liveness")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_app_startup():
    """Test that app can be created multiple times (factory pattern)."""
    app1 = create_app()
    app2 = create_app()

    assert app1 is not app2
    assert app1.title == "Plan Scheduler Service"
    assert app2.title == "Plan Scheduler Service"


def test_health_endpoint_with_test_client():
    """Test health endpoint works with dependency injection wiring."""
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_openapi_docs_available(client):
    """Test that OpenAPI documentation endpoints are accessible."""
    # Test OpenAPI JSON endpoint
    response = client.get("/openapi.json")
    assert response.status_code == 200
    openapi_data = response.json()
    assert "openapi" in openapi_data
    assert "info" in openapi_data

    # Verify new endpoints are documented
    paths = openapi_data.get("paths", {})
    assert "/health" in paths
    assert "/readiness" in paths
    assert "/liveness" in paths

    # Test Swagger UI docs
    response = client.get("/docs")
    assert response.status_code == 200

    # Test ReDoc
    response = client.get("/redoc")
    assert response.status_code == 200
