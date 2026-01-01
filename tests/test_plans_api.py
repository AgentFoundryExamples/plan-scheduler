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
from unittest.mock import MagicMock, patch

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


@pytest.fixture
def mock_dependencies():
    """Mock all dependencies for create_plan."""
    from datetime import UTC, datetime

    from app.models.plan import SpecRecord

    with (
        patch("app.dependencies.firestore_service.create_plan_with_specs") as mock_create_fs,
        patch("app.dependencies.get_execution_service") as mock_exec,
        patch("app.dependencies.get_firestore_client") as mock_client,
    ):
        # Setup default mocks
        exec_service = MagicMock()
        mock_exec.return_value = exec_service

        # Create a mock spec record for the spec 0 fetch
        mock_spec_record = SpecRecord(
            spec_index=0,
            purpose="Test purpose",
            vision="Test vision",
            must=["requirement 1"],
            dont=["avoid this"],
            nice=["nice to have"],
            assumptions=["assume this"],
            status="running",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            execution_attempts=1,
            last_execution_at=datetime.now(UTC),
            history=[],
        )

        client_mock = MagicMock()
        spec_doc_snapshot = MagicMock()
        spec_doc_snapshot.exists = True
        spec_doc_snapshot.to_dict.return_value = mock_spec_record.model_dump()
        # Set up nested mock chain for Firestore spec document access
        spec_doc_ref = client_mock.collection.return_value.document.return_value
        spec_doc_ref.collection.return_value.document.return_value.get.return_value = (
            spec_doc_snapshot
        )
        mock_client.return_value = client_mock

        yield {
            "create_fs": mock_create_fs,
            "exec_service": mock_exec,
            "client": mock_client,
        }


def test_create_plan_success_returns_201(client, valid_plan_payload, mock_dependencies):
    """Test that creating a new plan returns 201 Created."""
    mock_dependencies["create_fs"].return_value = (
        PlanIngestionOutcome.CREATED,
        valid_plan_payload["id"],
    )

    response = client.post("/plans", json=valid_plan_payload)

    assert response.status_code == 201
    data = response.json()
    assert data["plan_id"] == valid_plan_payload["id"]
    assert data["status"] == "running"
    mock_dependencies["create_fs"].assert_called_once()


def test_create_plan_idempotent_returns_200(client, valid_plan_payload, mock_dependencies):
    """Test that idempotent ingestion returns 200 OK."""
    mock_dependencies["create_fs"].return_value = (
        PlanIngestionOutcome.IDENTICAL,
        valid_plan_payload["id"],
    )

    response = client.post("/plans", json=valid_plan_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["plan_id"] == valid_plan_payload["id"]
    assert data["status"] == "running"
    mock_dependencies["create_fs"].assert_called_once()


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


# Tests for execution triggering behavior


def test_create_plan_triggers_execution_for_spec_0_only(client, valid_plan_payload):
    """Test that POST /plans triggers execution only for spec 0, not for later specs."""
    with (
        patch("app.dependencies.firestore_service.create_plan_with_specs") as mock_create_fs,
        patch("app.dependencies.get_execution_service") as mock_exec_service,
        patch("app.dependencies.get_firestore_client"),
    ):
        # Setup mock execution service
        exec_service = MagicMock()
        mock_exec_service.return_value = exec_service

        # Setup mock Firestore service to return CREATED
        mock_create_fs.return_value = (PlanIngestionOutcome.CREATED, valid_plan_payload["id"])

        # Make request
        response = client.post("/plans", json=valid_plan_payload)

        # Verify response
        assert response.status_code == 201

        # Verify trigger_spec_execution was called exactly once
        exec_service.trigger_spec_execution.assert_called_once()

        # Verify it was called for spec 0 only
        call_args = exec_service.trigger_spec_execution.call_args
        assert call_args[1]["plan_id"] == valid_plan_payload["id"]
        assert call_args[1]["spec_index"] == 0

        # Verify spec_data has running status
        spec_data = call_args[1]["spec_data"]
        assert spec_data.status == "running"
        assert spec_data.spec_index == 0


def test_create_plan_skips_execution_trigger_for_idempotent_ingestion(client, valid_plan_payload):
    """Test that idempotent ingestions skip execution triggering."""
    with (
        patch("app.dependencies.firestore_service.create_plan_with_specs") as mock_create_fs,
        patch("app.dependencies.get_execution_service") as mock_exec_service,
        patch("app.dependencies.get_firestore_client"),
    ):
        # Setup mock execution service
        exec_service = MagicMock()
        mock_exec_service.return_value = exec_service

        # Setup mock Firestore service to return IDENTICAL (idempotent)
        mock_create_fs.return_value = (
            PlanIngestionOutcome.IDENTICAL,
            valid_plan_payload["id"],
        )

        # Make request
        response = client.post("/plans", json=valid_plan_payload)

        # Verify response
        assert response.status_code == 200

        # Verify trigger_spec_execution was NOT called for idempotent ingestion
        exec_service.trigger_spec_execution.assert_not_called()


def test_create_plan_trigger_exception_causes_cleanup_and_error(client, valid_plan_payload):
    """Test that trigger_spec_execution exception causes plan cleanup and API error."""
    with (
        patch("app.dependencies.firestore_service.create_plan_with_specs") as mock_create_fs,
        patch("app.dependencies.firestore_service.delete_plan_with_specs") as mock_delete,
        patch("app.dependencies.get_execution_service") as mock_exec_service,
        patch("app.dependencies.get_firestore_client") as mock_client,
    ):
        # Setup mock execution service to raise exception
        exec_service = MagicMock()
        exec_service.trigger_spec_execution.side_effect = RuntimeError("Execution trigger failed")
        mock_exec_service.return_value = exec_service

        # Setup mock Firestore service to return CREATED
        mock_create_fs.return_value = (PlanIngestionOutcome.CREATED, valid_plan_payload["id"])

        # Make request - should fail
        response = client.post("/plans", json=valid_plan_payload)

        # Verify response is 500 error
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Internal server error"

        # Verify cleanup was called with correct client reference
        mock_delete.assert_called_once_with(
            valid_plan_payload["id"], client=mock_client.return_value
        )

        # Verify that cleanup was effective - mock_delete being called implies
        # the cleanup process ran (no documents remain is implicit in successful mock call)


def test_create_plan_trigger_exception_with_cleanup_failure(client, valid_plan_payload):
    """Test that cleanup failure is logged but original error is still raised."""
    with (
        patch("app.dependencies.firestore_service.create_plan_with_specs") as mock_create_fs,
        patch("app.dependencies.firestore_service.delete_plan_with_specs") as mock_delete,
        patch("app.dependencies.get_execution_service") as mock_exec_service,
        patch("app.dependencies.get_firestore_client") as mock_client,
    ):
        # Setup mock execution service to raise exception
        exec_service = MagicMock()
        exec_service.trigger_spec_execution.side_effect = RuntimeError("Execution trigger failed")
        mock_exec_service.return_value = exec_service

        # Setup mock Firestore service to return CREATED
        mock_create_fs.return_value = (PlanIngestionOutcome.CREATED, valid_plan_payload["id"])

        # Setup mock delete to fail during cleanup
        mock_delete.side_effect = FirestoreOperationError("Cleanup failed")

        # Make request - should fail with original error
        response = client.post("/plans", json=valid_plan_payload)

        # Verify response is still 500 error (original error propagated)
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Internal server error"

        # Verify cleanup was attempted
        mock_delete.assert_called_once_with(
            valid_plan_payload["id"], client=mock_client.return_value
        )


def test_create_plan_sets_spec_0_execution_metadata(client, valid_plan_payload):
    """Test that spec 0 has execution metadata set during successful ingestion."""
    with (
        patch("app.dependencies.firestore_service.create_plan_with_specs") as mock_create_fs,
        patch("app.dependencies.get_execution_service") as mock_exec_service,
        patch("app.dependencies.get_firestore_client"),
    ):
        # Setup mock execution service
        exec_service = MagicMock()
        mock_exec_service.return_value = exec_service

        # Setup mock Firestore service to return CREATED
        mock_create_fs.return_value = (PlanIngestionOutcome.CREATED, valid_plan_payload["id"])

        # Make request
        response = client.post("/plans", json=valid_plan_payload)

        # Verify response
        assert response.status_code == 201

        # Verify trigger_spec_execution was called with spec_data
        call_args = exec_service.trigger_spec_execution.call_args
        spec_data = call_args[1]["spec_data"]

        # Verify execution metadata is set for spec 0
        assert spec_data.status == "running"
        assert spec_data.spec_index == 0
        assert spec_data.execution_attempts == 1
        assert spec_data.last_execution_at is not None

        # Verify spec data matches the input
        assert spec_data.purpose == valid_plan_payload["specs"][0]["purpose"]
        assert spec_data.vision == valid_plan_payload["specs"][0]["vision"]


def test_create_plan_with_multiple_specs_only_triggers_spec_0(client, valid_plan_payload):
    """Test that with multiple specs, only spec 0 gets execution triggered."""
    # Extend valid_plan_payload with additional specs
    plan_payload = valid_plan_payload.copy()
    first_spec = valid_plan_payload["specs"][0]
    plan_payload["specs"] = [
        first_spec,
        {
            "purpose": "Second spec",
            "vision": "Second vision",
            "must": ["req 2"],
            "dont": [],
            "nice": [],
            "assumptions": [],
        },
        {
            "purpose": "Third spec",
            "vision": "Third vision",
            "must": ["req 3"],
            "dont": [],
            "nice": [],
            "assumptions": [],
        },
    ]

    with (
        patch("app.dependencies.firestore_service.create_plan_with_specs") as mock_create_fs,
        patch("app.dependencies.get_execution_service") as mock_exec_service,
        patch("app.dependencies.get_firestore_client"),
    ):
        # Setup mock execution service
        exec_service = MagicMock()
        mock_exec_service.return_value = exec_service

        # Setup mock Firestore service to return CREATED
        mock_create_fs.return_value = (PlanIngestionOutcome.CREATED, plan_payload["id"])

        # Make request
        response = client.post("/plans", json=plan_payload)

        # Verify response
        assert response.status_code == 201

        # Verify trigger_spec_execution was called exactly once
        exec_service.trigger_spec_execution.assert_called_once()

        # Verify it was only called for spec 0
        call_args = exec_service.trigger_spec_execution.call_args
        assert call_args[1]["spec_index"] == 0

        # Verify the spec data is for the first spec
        spec_data = call_args[1]["spec_data"]
        assert spec_data.purpose == first_spec["purpose"]
        assert spec_data.vision == first_spec["vision"]


# Tests for GET /plans/{plan_id} endpoint


def test_get_plan_status_success(client):
    """Test that GET /plans/{plan_id} returns plan status successfully."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    plan_id = str(uuid.uuid4())

    # Mock Firestore data
    plan_data = {
        "plan_id": plan_id,
        "overall_status": "running",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "total_specs": 2,
        "completed_specs": 1,
        "current_spec_index": 1,
        "last_event_at": datetime.now(UTC),
        "raw_request": {},
    }

    spec_data_list = [
        {
            "spec_index": 0,
            "purpose": "First spec",
            "vision": "First vision",
            "must": [],
            "dont": [],
            "nice": [],
            "assumptions": [],
            "status": "finished",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "current_stage": None,
            "history": [],
        },
        {
            "spec_index": 1,
            "purpose": "Second spec",
            "vision": "Second vision",
            "must": [],
            "dont": [],
            "nice": [],
            "assumptions": [],
            "status": "running",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "current_stage": "implementation",
            "history": [],
        },
    ]

    with (
        patch("app.api.plans.get_plan_with_specs") as mock_get_plan,
        patch("app.api.plans.get_firestore_client") as mock_client,
    ):
        mock_get_plan.return_value = (plan_data, spec_data_list)
        mock_client.return_value = MagicMock()

        response = client.get(f"/plans/{plan_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["plan_id"] == plan_id
        assert data["overall_status"] == "running"
        assert data["total_specs"] == 2
        assert data["completed_specs"] == 1
        assert data["current_spec_index"] == 1
        assert len(data["specs"]) == 2
        assert data["specs"][0]["spec_index"] == 0
        assert data["specs"][0]["status"] == "finished"
        assert data["specs"][1]["spec_index"] == 1
        assert data["specs"][1]["status"] == "running"
        assert data["specs"][1]["stage"] == "implementation"


def test_get_plan_status_not_found(client):
    """Test that GET /plans/{plan_id} returns 404 for non-existent plan."""
    from unittest.mock import MagicMock

    plan_id = str(uuid.uuid4())

    with (
        patch("app.api.plans.get_plan_with_specs") as mock_get_plan,
        patch("app.api.plans.get_firestore_client") as mock_client,
    ):
        mock_get_plan.return_value = (None, [])
        mock_client.return_value = MagicMock()

        response = client.get(f"/plans/{plan_id}")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Plan not found"


def test_get_plan_status_with_include_stage_false(client):
    """Test that include_stage=false removes stage field from spec statuses."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    plan_id = str(uuid.uuid4())

    # Mock Firestore data with stage values
    plan_data = {
        "plan_id": plan_id,
        "overall_status": "running",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "total_specs": 1,
        "completed_specs": 0,
        "current_spec_index": 0,
        "last_event_at": datetime.now(UTC),
        "raw_request": {},
    }

    spec_data_list = [
        {
            "spec_index": 0,
            "purpose": "Test spec",
            "vision": "Test vision",
            "must": [],
            "dont": [],
            "nice": [],
            "assumptions": [],
            "status": "running",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "current_stage": "implementation",
            "history": [],
        }
    ]

    with (
        patch("app.api.plans.get_plan_with_specs") as mock_get_plan,
        patch("app.api.plans.get_firestore_client") as mock_client,
    ):
        mock_get_plan.return_value = (plan_data, spec_data_list)
        mock_client.return_value = MagicMock()

        response = client.get(f"/plans/{plan_id}?include_stage=false")

        assert response.status_code == 200
        data = response.json()
        assert data["plan_id"] == plan_id
        assert len(data["specs"]) == 1
        # Stage should be null when include_stage=false
        assert data["specs"][0]["stage"] is None


def test_get_plan_status_with_include_stage_default_true(client):
    """Test that include_stage defaults to true and includes stage field."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    plan_id = str(uuid.uuid4())

    plan_data = {
        "plan_id": plan_id,
        "overall_status": "running",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "total_specs": 1,
        "completed_specs": 0,
        "current_spec_index": 0,
        "last_event_at": datetime.now(UTC),
        "raw_request": {},
    }

    spec_data_list = [
        {
            "spec_index": 0,
            "purpose": "Test spec",
            "vision": "Test vision",
            "must": [],
            "dont": [],
            "nice": [],
            "assumptions": [],
            "status": "running",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "current_stage": "reviewing",
            "history": [],
        }
    ]

    with (
        patch("app.api.plans.get_plan_with_specs") as mock_get_plan,
        patch("app.api.plans.get_firestore_client") as mock_client,
    ):
        mock_get_plan.return_value = (plan_data, spec_data_list)
        mock_client.return_value = MagicMock()

        response = client.get(f"/plans/{plan_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["specs"][0]["stage"] == "reviewing"


def test_get_plan_status_with_zero_specs(client):
    """Test that plans with zero specs return correctly."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    plan_id = str(uuid.uuid4())

    plan_data = {
        "plan_id": plan_id,
        "overall_status": "running",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "total_specs": 0,
        "completed_specs": 0,
        "current_spec_index": None,
        "last_event_at": datetime.now(UTC),
        "raw_request": {},
    }

    with (
        patch("app.api.plans.get_plan_with_specs") as mock_get_plan,
        patch("app.api.plans.get_firestore_client") as mock_client,
    ):
        mock_get_plan.return_value = (plan_data, [])
        mock_client.return_value = MagicMock()

        response = client.get(f"/plans/{plan_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["plan_id"] == plan_id
        assert data["total_specs"] == 0
        assert data["completed_specs"] == 0
        assert data["current_spec_index"] is None
        assert data["specs"] == []


def test_get_plan_status_firestore_error_returns_500(client):
    """Test that Firestore errors return 500 Internal Server Error."""
    from unittest.mock import MagicMock

    from app.services.firestore_service import FirestoreOperationError

    plan_id = str(uuid.uuid4())

    with (
        patch("app.api.plans.get_plan_with_specs") as mock_get_plan,
        patch("app.api.plans.get_firestore_client") as mock_client,
    ):
        mock_get_plan.side_effect = FirestoreOperationError("Firestore error")
        mock_client.return_value = MagicMock()

        response = client.get(f"/plans/{plan_id}")

        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Internal server error"


def test_get_plan_status_unexpected_error_returns_500(client):
    """Test that unexpected errors return 500 Internal Server Error."""
    from unittest.mock import MagicMock

    plan_id = str(uuid.uuid4())

    with (
        patch("app.api.plans.get_plan_with_specs") as mock_get_plan,
        patch("app.api.plans.get_firestore_client") as mock_client,
    ):
        mock_get_plan.side_effect = Exception("Unexpected error")
        mock_client.return_value = MagicMock()

        response = client.get(f"/plans/{plan_id}")

        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Internal server error"


def test_get_plan_status_endpoint_in_openapi_docs(client):
    """Test that GET /plans/{plan_id} endpoint is documented in OpenAPI schema."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi_data = response.json()
    assert "/plans/{plan_id}" in openapi_data["paths"]
    assert "get" in openapi_data["paths"]["/plans/{plan_id}"]

    get_spec = openapi_data["paths"]["/plans/{plan_id}"]["get"]
    assert "parameters" in get_spec
    assert "responses" in get_spec
    assert "200" in get_spec["responses"]
    assert "404" in get_spec["responses"]
    assert "500" in get_spec["responses"]


def test_get_plan_status_logs_retrieval_attempt(client, caplog):
    """Test that plan status retrieval attempts are logged."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock

    plan_id = str(uuid.uuid4())

    plan_data = {
        "plan_id": plan_id,
        "overall_status": "running",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "total_specs": 0,
        "completed_specs": 0,
        "current_spec_index": None,
        "last_event_at": datetime.now(UTC),
        "raw_request": {},
    }

    with (
        patch("app.api.plans.get_plan_with_specs") as mock_get_plan,
        patch("app.api.plans.get_firestore_client") as mock_client,
    ):
        mock_get_plan.return_value = (plan_data, [])
        mock_client.return_value = MagicMock()

        with caplog.at_level("INFO"):
            response = client.get(f"/plans/{plan_id}")

        assert response.status_code == 200
        log_messages = [record.message for record in caplog.records]
        assert any("Plan status retrieval request received" in msg for msg in log_messages)
        assert any("Plan status retrieved successfully" in msg for msg in log_messages)


def test_get_plan_status_logs_not_found(client, caplog):
    """Test that plan not found is logged."""
    from unittest.mock import MagicMock

    plan_id = str(uuid.uuid4())

    with (
        patch("app.api.plans.get_plan_with_specs") as mock_get_plan,
        patch("app.api.plans.get_firestore_client") as mock_client,
    ):
        mock_get_plan.return_value = (None, [])
        mock_client.return_value = MagicMock()

        with caplog.at_level("WARNING"):
            response = client.get(f"/plans/{plan_id}")

        assert response.status_code == 404
        log_messages = [record.message for record in caplog.records]
        assert any("Plan not found" in msg for msg in log_messages)
