"""Tests for health check endpoint."""

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
    
    # Test Swagger UI docs
    response = client.get("/docs")
    assert response.status_code == 200
    
    # Test ReDoc
    response = client.get("/redoc")
    assert response.status_code == 200
