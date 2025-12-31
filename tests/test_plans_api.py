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
"""Tests for plan ingestion API endpoints."""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.firestore_service import (
    FirestoreOperationError,
    PlanConflictError,
    PlanIngestionOutcome,
)


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def valid_plan_payload():
    """Create a valid plan payload for testing."""
    return {
        "id": str(uuid.uuid4()),
        "specs": [
            {
                "purpose": "Test purpose",
                "vision": "Test vision",
                "must": ["requirement 1"],
                "dont": ["avoid this"],
                "nice": ["nice to have"],
                "assumptions": ["assume this"],
            }
        ],
    }


def test_create_plan_success_returns_201(client, valid_plan_payload):
    """Test that creating a new plan returns 201 Created."""
    with patch("app.dependencies.create_plan") as mock_create:
        mock_create.return_value = (PlanIngestionOutcome.CREATED, valid_plan_payload["id"])

        response = client.post("/plans", json=valid_plan_payload)

        assert response.status_code == 201
        data = response.json()
        assert data["plan_id"] == valid_plan_payload["id"]
        assert data["status"] == "running"
        mock_create.assert_called_once()


def test_create_plan_idempotent_returns_200(client, valid_plan_payload):
    """Test that idempotent ingestion returns 200 OK."""
    with patch("app.dependencies.create_plan") as mock_create:
        mock_create.return_value = (PlanIngestionOutcome.IDENTICAL, valid_plan_payload["id"])

        response = client.post("/plans", json=valid_plan_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["plan_id"] == valid_plan_payload["id"]
        assert data["status"] == "running"
        mock_create.assert_called_once()


def test_create_plan_conflict_returns_409(client, valid_plan_payload):
    """Test that plan conflict returns 409 Conflict."""
    with patch("app.dependencies.create_plan") as mock_create:
        mock_create.side_effect = PlanConflictError(
            "Plan exists with different body",
            stored_digest="abc123",
            incoming_digest="def456",
        )

        response = client.post("/plans", json=valid_plan_payload)

        assert response.status_code == 409
        data = response.json()
        assert "detail" in data
        assert "already exists with different body" in data["detail"]


def test_create_plan_invalid_uuid_returns_400(client):
    """Test that invalid UUID returns 400 Bad Request."""
    invalid_payload = {
        "id": "not-a-uuid",
        "specs": [
            {
                "purpose": "Test purpose",
                "vision": "Test vision",
            }
        ],
    }

    response = client.post("/plans", json=invalid_payload)

    assert response.status_code == 422  # FastAPI validation error
    data = response.json()
    assert "detail" in data


def test_create_plan_empty_specs_returns_400(client):
    """Test that empty specs array returns 400 Bad Request."""
    invalid_payload = {
        "id": str(uuid.uuid4()),
        "specs": [],
    }

    response = client.post("/plans", json=invalid_payload)

    assert response.status_code == 422  # FastAPI validation error
    data = response.json()
    assert "detail" in data


def test_create_plan_missing_required_fields_returns_400(client):
    """Test that missing required fields returns 400 Bad Request."""
    invalid_payload = {
        "id": str(uuid.uuid4()),
        "specs": [
            {
                "purpose": "Test purpose",
                # Missing "vision"
            }
        ],
    }

    response = client.post("/plans", json=invalid_payload)

    assert response.status_code == 422  # FastAPI validation error
    data = response.json()
    assert "detail" in data


def test_create_plan_firestore_error_returns_500(client, valid_plan_payload):
    """Test that Firestore operation error returns 500 Internal Server Error."""
    with patch("app.dependencies.create_plan") as mock_create:
        mock_create.side_effect = FirestoreOperationError("Firestore operation failed")

        response = client.post("/plans", json=valid_plan_payload)

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert data["detail"] == "Internal server error"
        # Should not leak internal error details
        assert "Firestore" not in data["detail"]


def test_create_plan_unexpected_error_returns_500(client, valid_plan_payload):
    """Test that unexpected errors return 500 Internal Server Error."""
    with patch("app.dependencies.create_plan") as mock_create:
        mock_create.side_effect = Exception("Unexpected error")

        response = client.post("/plans", json=valid_plan_payload)

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert data["detail"] == "Internal server error"
        # Should not leak stack traces
        assert "Exception" not in data["detail"]
        assert "Unexpected error" not in data["detail"]


def test_create_plan_malformed_json_returns_400(client):
    """Test that malformed JSON returns 400 Bad Request."""
    response = client.post(
        "/plans",
        data="not valid json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_create_plan_endpoint_in_openapi_docs(client):
    """Test that POST /plans endpoint is documented in OpenAPI schema."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi_data = response.json()
    assert "/plans" in openapi_data["paths"]
    assert "post" in openapi_data["paths"]["/plans"]

    post_spec = openapi_data["paths"]["/plans"]["post"]
    assert "requestBody" in post_spec
    assert "responses" in post_spec
    assert "201" in post_spec["responses"]
    assert "200" in post_spec["responses"]
    assert "409" in post_spec["responses"]
    assert "400" in post_spec["responses"]
    assert "500" in post_spec["responses"]


def test_create_plan_with_multiple_specs(client):
    """Test that creating a plan with multiple specs works correctly."""
    plan_payload = {
        "id": str(uuid.uuid4()),
        "specs": [
            {
                "purpose": "First spec",
                "vision": "First vision",
                "must": ["req 1"],
                "dont": [],
                "nice": [],
                "assumptions": [],
            },
            {
                "purpose": "Second spec",
                "vision": "Second vision",
                "must": ["req 2"],
                "dont": ["avoid"],
                "nice": ["nice"],
                "assumptions": ["assume"],
            },
        ],
    }

    with patch("app.dependencies.create_plan") as mock_create:
        mock_create.return_value = (PlanIngestionOutcome.CREATED, plan_payload["id"])

        response = client.post("/plans", json=plan_payload)

        assert response.status_code == 201
        data = response.json()
        assert data["plan_id"] == plan_payload["id"]
        assert data["status"] == "running"


def test_create_plan_with_empty_list_fields(client):
    """Test that specs with empty list fields are accepted."""
    plan_payload = {
        "id": str(uuid.uuid4()),
        "specs": [
            {
                "purpose": "Test purpose",
                "vision": "Test vision",
                "must": [],
                "dont": [],
                "nice": [],
                "assumptions": [],
            }
        ],
    }

    with patch("app.dependencies.create_plan") as mock_create:
        mock_create.return_value = (PlanIngestionOutcome.CREATED, plan_payload["id"])

        response = client.post("/plans", json=plan_payload)

        assert response.status_code == 201
        data = response.json()
        assert data["plan_id"] == plan_payload["id"]


def test_create_plan_content_type_json(client, valid_plan_payload):
    """Test that the endpoint returns JSON content type."""
    with patch("app.dependencies.create_plan") as mock_create:
        mock_create.return_value = (PlanIngestionOutcome.CREATED, valid_plan_payload["id"])

        response = client.post("/plans", json=valid_plan_payload)

        assert response.status_code == 201
        assert "application/json" in response.headers["content-type"]


def test_create_plan_logs_ingestion_attempt(client, valid_plan_payload, caplog):
    """Test that ingestion attempts are logged."""
    with patch("app.dependencies.create_plan") as mock_create:
        mock_create.return_value = (PlanIngestionOutcome.CREATED, valid_plan_payload["id"])

        with caplog.at_level("INFO"):
            response = client.post("/plans", json=valid_plan_payload)

        assert response.status_code == 201
        # Check that logs contain relevant information
        log_messages = [record.message for record in caplog.records]
        assert any("Plan ingestion request received" in msg for msg in log_messages)


def test_create_plan_logs_idempotent_ingestion(client, valid_plan_payload, caplog):
    """Test that idempotent ingestions are logged explicitly."""
    with patch("app.dependencies.create_plan") as mock_create:
        mock_create.return_value = (PlanIngestionOutcome.IDENTICAL, valid_plan_payload["id"])

        with caplog.at_level("INFO"):
            response = client.post("/plans", json=valid_plan_payload)

        assert response.status_code == 200
        # Check that logs mention idempotent behavior
        log_messages = [record.message for record in caplog.records]
        assert any("Idempotent ingestion" in msg for msg in log_messages)


def test_create_plan_logs_conflict(client, valid_plan_payload, caplog):
    """Test that conflicts are logged."""
    with patch("app.dependencies.create_plan") as mock_create:
        mock_create.side_effect = PlanConflictError(
            "Plan exists with different body",
            stored_digest="abc123",
            incoming_digest="def456",
        )

        with caplog.at_level("WARNING"):
            response = client.post("/plans", json=valid_plan_payload)

        assert response.status_code == 409
        # Check that logs contain conflict information
        log_messages = [record.message for record in caplog.records]
        assert any("Plan ingestion conflict" in msg for msg in log_messages)


def test_create_plan_logs_firestore_error(client, valid_plan_payload, caplog):
    """Test that Firestore errors are logged with details."""
    with patch("app.dependencies.create_plan") as mock_create:
        mock_create.side_effect = FirestoreOperationError("Firestore operation failed")

        with caplog.at_level("ERROR"):
            response = client.post("/plans", json=valid_plan_payload)

        assert response.status_code == 500
        # Check that logs contain error information
        log_messages = [record.message for record in caplog.records]
        assert any("Plan ingestion failed due to Firestore error" in msg for msg in log_messages)
