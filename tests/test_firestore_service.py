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
"""Tests for Firestore service integration."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from google.api_core import exceptions as gcp_exceptions
from google.auth import exceptions as auth_exceptions

from app.services import firestore_service
from app.services.firestore_service import (
    FirestoreConfigurationError,
    FirestoreConnectionError,
    PlanIngestionOutcome,
    get_client,
    smoke_test,
)


@pytest.fixture(autouse=True)
def clear_client_cache():
    """Clear the client cache before and after each test."""
    get_client.cache_clear()
    yield
    get_client.cache_clear()


@pytest.fixture
def mock_firestore_client():
    """Create a mock Firestore client."""
    with patch("app.services.firestore_service.firestore.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_settings():
    """Create a mock settings object with Firestore configuration."""
    with patch("app.services.firestore_service.get_settings") as mock_get_settings:
        mock_settings_obj = MagicMock()
        mock_settings_obj.FIRESTORE_PROJECT_ID = "test-project-id"
        mock_get_settings.return_value = mock_settings_obj
        yield mock_settings_obj


def test_get_client_initializes_with_valid_config(mock_settings, mock_firestore_client):
    """Test that get_client initializes Firestore client with valid configuration."""
    client = get_client()

    assert client == mock_firestore_client
    firestore_service.firestore.Client.assert_called_once_with(project="test-project-id")


def test_get_client_raises_error_when_project_id_missing(mock_firestore_client):
    """Test that get_client raises clear error when FIRESTORE_PROJECT_ID is not set."""
    with patch("app.services.firestore_service.get_settings") as mock_get_settings:
        mock_settings_obj = MagicMock()
        mock_settings_obj.FIRESTORE_PROJECT_ID = ""
        mock_get_settings.return_value = mock_settings_obj

        with pytest.raises(FirestoreConfigurationError) as exc_info:
            get_client()

        assert "FIRESTORE_PROJECT_ID is not configured" in str(exc_info.value)
        assert "environment variable" in str(exc_info.value)


def test_get_client_raises_error_when_adc_not_available(mock_settings):
    """Test that get_client raises actionable error when ADC is not available."""
    with patch("app.services.firestore_service.firestore.Client") as mock_client_class:
        mock_client_class.side_effect = auth_exceptions.DefaultCredentialsError(
            "Could not automatically determine credentials"
        )

        with pytest.raises(FirestoreConfigurationError) as exc_info:
            get_client()

        error_msg = str(exc_info.value)
        assert "Application Default Credentials (ADC) not found" in error_msg
        assert "GOOGLE_APPLICATION_CREDENTIALS" in error_msg
        assert "gcloud auth application-default login" in error_msg


def test_get_client_singleton_behavior(mock_settings, mock_firestore_client):
    """Test that get_client returns the same instance on multiple calls."""
    client1 = get_client()
    client2 = get_client()

    assert client1 is client2
    # Client should only be instantiated once due to caching
    firestore_service.firestore.Client.assert_called_once()


def test_get_client_handles_generic_initialization_errors(mock_settings):
    """Test that get_client handles generic errors during initialization."""
    with patch("app.services.firestore_service.firestore.Client") as mock_client_class:
        mock_client_class.side_effect = Exception("Unexpected initialization error")

        with pytest.raises(FirestoreConfigurationError) as exc_info:
            get_client()

        assert "Failed to initialize Firestore client" in str(exc_info.value)


def test_smoke_test_successful_write_read_delete(mock_settings, mock_firestore_client):
    """Test that smoke_test successfully writes, reads, and deletes a document."""
    # Setup mock document reference and snapshot
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    mock_doc_snapshot.to_dict.return_value = {
        "test": True,
        "message": "Firestore connectivity test",
    }

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    mock_firestore_client.collection.return_value = mock_collection

    # Run smoke test
    smoke_test(mock_firestore_client)

    # Verify operations were called
    mock_firestore_client.collection.assert_called_once_with("plans_dev_test")
    mock_collection.document.assert_called_once()
    mock_doc_ref.set.assert_called_once()
    mock_doc_ref.get.assert_called_once()
    mock_doc_ref.delete.assert_called_once()


def test_smoke_test_uses_get_client_when_no_client_provided(mock_settings, mock_firestore_client):
    """Test that smoke_test uses get_client() when no client is provided."""
    # Setup mock document reference and snapshot
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    mock_doc_snapshot.to_dict.return_value = {"test": True}

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    mock_firestore_client.collection.return_value = mock_collection

    # Run smoke test without providing client
    smoke_test()

    # Verify get_client was used
    assert mock_firestore_client.collection.called


def test_smoke_test_raises_error_when_document_not_found(mock_firestore_client):
    """Test that smoke_test raises error when document is not found after write."""
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False  # Document doesn't exist

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    mock_firestore_client.collection.return_value = mock_collection

    with pytest.raises(FirestoreConnectionError) as exc_info:
        smoke_test(mock_firestore_client)

    assert "was not found after write" in str(exc_info.value)
    # Verify cleanup was still attempted
    mock_doc_ref.delete.assert_called_once()


def test_smoke_test_raises_error_when_data_validation_fails(mock_firestore_client):
    """Test that smoke_test raises error when retrieved data is invalid."""
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    mock_doc_snapshot.to_dict.return_value = {"test": False}  # Wrong data

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    mock_firestore_client.collection.return_value = mock_collection

    with pytest.raises(FirestoreConnectionError) as exc_info:
        smoke_test(mock_firestore_client)

    assert "data validation failed" in str(exc_info.value)
    # Verify cleanup was still attempted
    mock_doc_ref.delete.assert_called_once()


def test_smoke_test_handles_gcp_api_errors(mock_firestore_client):
    """Test that smoke_test handles GCP API errors gracefully."""
    mock_doc_ref = MagicMock()
    mock_doc_ref.set.side_effect = gcp_exceptions.PermissionDenied("Access denied")

    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    mock_firestore_client.collection.return_value = mock_collection

    with pytest.raises(FirestoreConnectionError) as exc_info:
        smoke_test(mock_firestore_client)

    error_msg = str(exc_info.value)
    assert "Firestore API error" in error_msg
    assert "permissions" in error_msg.lower()


def test_smoke_test_handles_network_timeouts(mock_firestore_client):
    """Test that smoke_test handles network timeouts appropriately."""
    mock_doc_ref = MagicMock()
    mock_doc_ref.set.side_effect = gcp_exceptions.DeadlineExceeded("Request timeout")

    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    mock_firestore_client.collection.return_value = mock_collection

    with pytest.raises(FirestoreConnectionError) as exc_info:
        smoke_test(mock_firestore_client)

    error_msg = str(exc_info.value)
    assert "Firestore API error" in error_msg
    assert "network" in error_msg.lower()


def test_smoke_test_handles_unexpected_errors(mock_firestore_client):
    """Test that smoke_test handles unexpected errors during operation."""
    mock_doc_ref = MagicMock()
    mock_doc_ref.set.side_effect = RuntimeError("Unexpected error")

    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    mock_firestore_client.collection.return_value = mock_collection

    with pytest.raises(FirestoreConnectionError) as exc_info:
        smoke_test(mock_firestore_client)

    assert "unexpected error" in str(exc_info.value).lower()


def test_smoke_test_cleanup_failure_does_not_mask_original_error(mock_firestore_client, caplog):
    """Test that cleanup failures don't mask the original error."""
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False  # Will cause original error
    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_doc_ref.delete.side_effect = Exception("Cleanup failed")  # Cleanup also fails

    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    mock_firestore_client.collection.return_value = mock_collection

    with caplog.at_level(logging.WARNING):
        with pytest.raises(FirestoreConnectionError) as exc_info:
            smoke_test(mock_firestore_client)

    # Original error should be raised
    assert "was not found after write" in str(exc_info.value)

    # Cleanup failure should be logged as warning
    warning_messages = [
        record.message for record in caplog.records if record.levelname == "WARNING"
    ]
    assert any("failed to clean up" in msg.lower() for msg in warning_messages)


def test_smoke_test_uses_unique_document_ids():
    """Test that smoke_test uses unique document IDs to avoid race conditions."""
    mock_client = MagicMock()
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    mock_doc_snapshot.to_dict.return_value = {"test": True}
    mock_doc_ref.get.return_value = mock_doc_snapshot

    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    mock_client.collection.return_value = mock_collection

    # Run smoke test twice
    smoke_test(mock_client)
    first_call_doc_id = mock_collection.document.call_args_list[0][0][0]

    mock_collection.reset_mock()
    smoke_test(mock_client)
    second_call_doc_id = mock_collection.document.call_args_list[0][0][0]

    # Document IDs should be different
    assert first_call_doc_id != second_call_doc_id
    assert first_call_doc_id.startswith("test_")
    assert second_call_doc_id.startswith("test_")


def test_smoke_test_successful_cleanup_even_on_success(mock_firestore_client):
    """Test that smoke_test always cleans up, even when test succeeds."""
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    mock_doc_snapshot.to_dict.return_value = {"test": True}

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    mock_firestore_client.collection.return_value = mock_collection

    # Run smoke test (should succeed)
    smoke_test(mock_firestore_client)

    # Verify cleanup was called
    mock_doc_ref.delete.assert_called_once()


def test_get_client_logs_initialization(mock_settings, mock_firestore_client, caplog):
    """Test that get_client logs successful initialization."""
    with caplog.at_level(logging.INFO):
        _ = get_client()  # Get client to trigger logging

    info_messages = [record.message for record in caplog.records if record.levelname == "INFO"]
    assert any("Firestore client initialized" in msg for msg in info_messages)
    assert any("test-project-id" in msg for msg in info_messages)


def test_smoke_test_logs_operations(mock_firestore_client, caplog):
    """Test that smoke_test logs its operations."""
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    mock_doc_snapshot.to_dict.return_value = {"test": True}

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    mock_firestore_client.collection.return_value = mock_collection

    with caplog.at_level(logging.INFO):
        smoke_test(mock_firestore_client)

    info_messages = [record.message for record in caplog.records if record.levelname == "INFO"]
    assert any("wrote test document" in msg for msg in info_messages)
    assert any("successfully read back" in msg for msg in info_messages)
    assert any("cleaned up test document" in msg for msg in info_messages)


# Tests for plan persistence functionality


@pytest.fixture
def sample_plan_in():
    """Create a sample PlanIn for testing."""
    from uuid import uuid4

    from app.models.plan import PlanIn, SpecIn

    return PlanIn(
        id=str(uuid4()),
        specs=[
            SpecIn(purpose="Test purpose 1", vision="Test vision 1", must=["must1"]),
            SpecIn(purpose="Test purpose 2", vision="Test vision 2", dont=["dont2"]),
        ],
    )


def test_compute_request_digest():
    """Test that request digest is computed consistently."""
    from app.services.firestore_service import _compute_request_digest

    request1 = {"id": "123", "specs": [{"purpose": "test"}]}
    request2 = {"specs": [{"purpose": "test"}], "id": "123"}  # Different order

    digest1 = _compute_request_digest(request1)
    digest2 = _compute_request_digest(request2)

    assert digest1 == digest2
    assert len(digest1) == 64  # SHA-256 hex digest


def test_compute_request_digest_different_content():
    """Test that different content produces different digests."""
    from app.services.firestore_service import _compute_request_digest

    request1 = {"id": "123", "specs": [{"purpose": "test1"}]}
    request2 = {"id": "123", "specs": [{"purpose": "test2"}]}

    digest1 = _compute_request_digest(request1)
    digest2 = _compute_request_digest(request2)

    assert digest1 != digest2


def test_check_plan_exists_returns_false_when_not_exists(mock_firestore_client, sample_plan_in):
    """Test that _check_plan_exists returns False when plan doesn't exist."""
    from app.services.firestore_service import _check_plan_exists

    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    exists, outcome, digest = _check_plan_exists(
        mock_firestore_client, sample_plan_in.id, sample_plan_in
    )

    assert exists is False
    assert outcome is None
    assert digest is None


def test_check_plan_exists_identical_request(mock_firestore_client, sample_plan_in):
    """Test that _check_plan_exists detects identical requests."""
    from app.services.firestore_service import (
        PlanIngestionOutcome,
        _check_plan_exists,
        _compute_request_digest,
    )

    raw_request = sample_plan_in.model_dump()
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    mock_doc_snapshot.to_dict.return_value = {"raw_request": raw_request, "total_specs": 2}

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    exists, outcome, digest = _check_plan_exists(
        mock_firestore_client, sample_plan_in.id, sample_plan_in
    )

    assert exists is True
    assert outcome == PlanIngestionOutcome.IDENTICAL
    assert digest == _compute_request_digest(raw_request)


def test_check_plan_exists_raises_conflict_different_request(mock_firestore_client, sample_plan_in):
    """Test that _check_plan_exists raises conflict for different requests."""
    from app.services.firestore_service import PlanConflictError, _check_plan_exists

    # Different raw_request stored
    different_request = sample_plan_in.model_dump()
    different_request["specs"][0]["purpose"] = "Different purpose"

    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    mock_doc_snapshot.to_dict.return_value = {"raw_request": different_request, "total_specs": 2}

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with pytest.raises(PlanConflictError) as exc_info:
        _check_plan_exists(mock_firestore_client, sample_plan_in.id, sample_plan_in)

    assert "different body" in str(exc_info.value)
    assert exc_info.value.stored_digest != exc_info.value.incoming_digest


def test_check_plan_exists_missing_raw_request_same_spec_count(
    mock_firestore_client, sample_plan_in, caplog
):
    """Test fallback when raw_request missing but spec counts match."""
    from app.services.firestore_service import PlanIngestionOutcome, _check_plan_exists

    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    # Missing raw_request, but same total_specs
    mock_doc_snapshot.to_dict.return_value = {"total_specs": 2}

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with caplog.at_level(logging.WARNING):
        exists, outcome, digest = _check_plan_exists(
            mock_firestore_client, sample_plan_in.id, sample_plan_in
        )

    assert exists is True
    assert outcome == PlanIngestionOutcome.IDENTICAL
    assert digest is None
    assert any("missing raw_request" in msg for msg in caplog.messages)


def test_check_plan_exists_missing_raw_request_different_spec_count(
    mock_firestore_client, sample_plan_in
):
    """Test fallback raises conflict when spec counts differ."""
    from app.services.firestore_service import PlanConflictError, _check_plan_exists

    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    # Missing raw_request, different total_specs
    mock_doc_snapshot.to_dict.return_value = {"total_specs": 5}

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with pytest.raises(PlanConflictError) as exc_info:
        _check_plan_exists(mock_firestore_client, sample_plan_in.id, sample_plan_in)

    assert "different spec count" in str(exc_info.value)
    assert "spec_count_5" in exc_info.value.stored_digest
    assert "spec_count_2" in exc_info.value.incoming_digest


def test_check_plan_exists_handles_firestore_errors(mock_firestore_client, sample_plan_in):
    """Test that _check_plan_exists handles Firestore API errors."""
    from app.services.firestore_service import FirestoreOperationError, _check_plan_exists

    mock_doc_ref = MagicMock()
    mock_doc_ref.get.side_effect = gcp_exceptions.PermissionDenied("Access denied")

    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with pytest.raises(FirestoreOperationError) as exc_info:
        _check_plan_exists(mock_firestore_client, sample_plan_in.id, sample_plan_in)

    assert "Firestore API error" in str(exc_info.value)


def test_create_plan_with_specs_creates_new_plan(mock_firestore_client, sample_plan_in, caplog):
    """Test that create_plan_with_specs creates a new plan successfully."""
    from app.services.firestore_service import PlanIngestionOutcome, create_plan_with_specs

    # Mock plan doesn't exist
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False
    mock_doc_ref.get.return_value = mock_doc_snapshot

    mock_batch = MagicMock()
    mock_firestore_client.batch.return_value = mock_batch
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with caplog.at_level(logging.INFO):
        outcome, plan_id = create_plan_with_specs(sample_plan_in, mock_firestore_client)

    assert outcome == PlanIngestionOutcome.CREATED
    assert plan_id == sample_plan_in.id

    # Verify batch operations
    assert mock_batch.set.call_count == 3  # 1 plan + 2 specs
    mock_batch.commit.assert_called_once()

    # Verify logging
    assert any("Created plan" in msg for msg in caplog.messages)


def test_create_plan_with_specs_first_spec_running_others_blocked(
    mock_firestore_client, sample_plan_in
):
    """Test that first spec is running and others are blocked."""
    from app.services.firestore_service import create_plan_with_specs

    # Mock plan doesn't exist
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False
    mock_doc_ref.get.return_value = mock_doc_snapshot

    mock_batch = MagicMock()
    mock_firestore_client.batch.return_value = mock_batch
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    create_plan_with_specs(sample_plan_in, mock_firestore_client)

    # Check the spec status in batch.set calls
    set_calls = mock_batch.set.call_args_list
    assert len(set_calls) == 3  # 1 plan + 2 specs

    # First call is plan metadata
    plan_data = set_calls[0][0][1]
    assert plan_data["overall_status"] == "running"
    assert plan_data["current_spec_index"] == 0
    assert plan_data["total_specs"] == 2
    assert plan_data["completed_specs"] == 0

    # Second call is spec 0 - should be running
    spec0_data = set_calls[1][0][1]
    assert spec0_data["status"] == "running"
    assert spec0_data["spec_index"] == 0

    # Third call is spec 1 - should be blocked
    spec1_data = set_calls[2][0][1]
    assert spec1_data["status"] == "blocked"
    assert spec1_data["spec_index"] == 1


def test_create_plan_with_specs_idempotent_success(mock_firestore_client, sample_plan_in, caplog):
    """Test that create_plan_with_specs returns idempotent success for identical requests."""
    from app.services.firestore_service import PlanIngestionOutcome, create_plan_with_specs

    # Mock plan exists with same raw_request
    raw_request = sample_plan_in.model_dump()
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    mock_doc_snapshot.to_dict.return_value = {"raw_request": raw_request, "total_specs": 2}
    mock_doc_ref.get.return_value = mock_doc_snapshot

    mock_batch = MagicMock()
    mock_firestore_client.batch.return_value = mock_batch
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with caplog.at_level(logging.INFO):
        outcome, plan_id = create_plan_with_specs(sample_plan_in, mock_firestore_client)

    assert outcome == PlanIngestionOutcome.IDENTICAL
    assert plan_id == sample_plan_in.id

    # Verify batch was NOT committed (no duplicate writes)
    mock_batch.commit.assert_not_called()

    # Verify logging
    assert any("already exists with identical payload" in msg for msg in caplog.messages)


def test_create_plan_with_specs_raises_conflict(mock_firestore_client, sample_plan_in):
    """Test that create_plan_with_specs raises conflict for different requests."""
    from app.services.firestore_service import PlanConflictError, create_plan_with_specs

    # Mock plan exists with different raw_request
    different_request = sample_plan_in.model_dump()
    different_request["specs"][0]["purpose"] = "Different purpose"

    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    mock_doc_snapshot.to_dict.return_value = {"raw_request": different_request, "total_specs": 2}
    mock_doc_ref.get.return_value = mock_doc_snapshot

    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with pytest.raises(PlanConflictError) as exc_info:
        create_plan_with_specs(sample_plan_in, mock_firestore_client)

    assert "different body" in str(exc_info.value)


def test_create_plan_with_specs_handles_batch_failure(mock_firestore_client, sample_plan_in):
    """Test that create_plan_with_specs handles batch commit failures."""
    from app.services.firestore_service import FirestoreOperationError, create_plan_with_specs

    # Mock plan doesn't exist
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False
    mock_doc_ref.get.return_value = mock_doc_snapshot

    mock_batch = MagicMock()
    mock_batch.commit.side_effect = gcp_exceptions.DeadlineExceeded("Timeout")
    mock_firestore_client.batch.return_value = mock_batch
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with pytest.raises(FirestoreOperationError) as exc_info:
        create_plan_with_specs(sample_plan_in, mock_firestore_client)

    assert "Firestore API error" in str(exc_info.value)


def test_create_plan_with_specs_uses_default_client_when_none_provided(
    mock_settings, mock_firestore_client, sample_plan_in
):
    """Test that create_plan_with_specs uses get_client() when client not provided."""
    from app.services.firestore_service import create_plan_with_specs

    # Mock plan doesn't exist
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False
    mock_doc_ref.get.return_value = mock_doc_snapshot

    mock_batch = MagicMock()
    mock_firestore_client.batch.return_value = mock_batch
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    # Call without client parameter
    outcome, plan_id = create_plan_with_specs(sample_plan_in)

    assert outcome == PlanIngestionOutcome.CREATED
    assert plan_id == sample_plan_in.id


def test_create_plan_with_specs_stores_raw_request(mock_firestore_client, sample_plan_in):
    """Test that create_plan_with_specs stores the raw request."""
    from app.services.firestore_service import create_plan_with_specs

    # Mock plan doesn't exist
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False
    mock_doc_ref.get.return_value = mock_doc_snapshot

    mock_batch = MagicMock()
    mock_firestore_client.batch.return_value = mock_batch
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    create_plan_with_specs(sample_plan_in, mock_firestore_client)

    # Check the plan data stored
    set_calls = mock_batch.set.call_args_list
    plan_data = set_calls[0][0][1]

    assert "raw_request" in plan_data
    assert plan_data["raw_request"]["id"] == sample_plan_in.id
    assert len(plan_data["raw_request"]["specs"]) == 2


def test_create_plan_with_specs_uses_string_doc_ids_for_specs(
    mock_firestore_client, sample_plan_in
):
    """Test that spec documents use string indices as document IDs."""
    from app.services.firestore_service import create_plan_with_specs

    # Mock plan doesn't exist
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False
    mock_doc_ref.get.return_value = mock_doc_snapshot

    mock_spec_collection = MagicMock()
    mock_doc_ref.collection.return_value = mock_spec_collection

    mock_batch = MagicMock()
    mock_firestore_client.batch.return_value = mock_batch
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    create_plan_with_specs(sample_plan_in, mock_firestore_client)

    # Verify spec document IDs are strings
    spec_doc_calls = mock_spec_collection.document.call_args_list
    assert len(spec_doc_calls) == 2
    assert spec_doc_calls[0][0][0] == "0"
    assert spec_doc_calls[1][0][0] == "1"
