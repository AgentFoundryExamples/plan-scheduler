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


def test_check_plan_exists_empty_document_raises_error(mock_firestore_client, sample_plan_in):
    """Test that empty document raises FirestoreOperationError."""
    from app.services.firestore_service import FirestoreOperationError, _check_plan_exists

    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = True
    # Document exists but is empty
    mock_doc_snapshot.to_dict.return_value = None

    mock_doc_ref.get.return_value = mock_doc_snapshot
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with pytest.raises(FirestoreOperationError) as exc_info:
        _check_plan_exists(mock_firestore_client, sample_plan_in.id, sample_plan_in)

    assert "exists but is empty" in str(exc_info.value)


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

    mock_transaction = MagicMock()
    mock_firestore_client.transaction.return_value = mock_transaction
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with caplog.at_level(logging.INFO):
        outcome, plan_id = create_plan_with_specs(sample_plan_in, mock_firestore_client)

    assert outcome == PlanIngestionOutcome.CREATED
    assert plan_id == sample_plan_in.id

    # Verify transaction operations
    assert mock_transaction.create.call_count == 3  # 1 plan + 2 specs

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

    mock_transaction = MagicMock()
    mock_firestore_client.transaction.return_value = mock_transaction
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    create_plan_with_specs(sample_plan_in, mock_firestore_client)

    # Check the spec status in transaction.create calls
    create_calls = mock_transaction.create.call_args_list
    assert len(create_calls) == 3  # 1 plan + 2 specs

    # First call is plan metadata
    plan_data = create_calls[0][0][1]
    assert plan_data["overall_status"] == "running"
    assert plan_data["current_spec_index"] == 0
    assert plan_data["total_specs"] == 2
    assert plan_data["completed_specs"] == 0

    # Second call is spec 0 - should be running
    spec0_data = create_calls[1][0][1]
    assert spec0_data["status"] == "running"
    assert spec0_data["spec_index"] == 0

    # Third call is spec 1 - should be blocked
    spec1_data = create_calls[2][0][1]
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

    mock_transaction = MagicMock()
    mock_firestore_client.transaction.return_value = mock_transaction
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with caplog.at_level(logging.INFO):
        outcome, plan_id = create_plan_with_specs(sample_plan_in, mock_firestore_client)

    assert outcome == PlanIngestionOutcome.IDENTICAL
    assert plan_id == sample_plan_in.id

    # Verify transaction.create was NOT called (no duplicate writes)
    mock_transaction.create.assert_not_called()

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
    """Test that create_plan_with_specs handles transaction failures."""
    from app.services.firestore_service import FirestoreOperationError, create_plan_with_specs

    # Mock plan doesn't exist
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False
    mock_doc_ref.get.return_value = mock_doc_snapshot

    # Make transaction.create raise an error
    mock_transaction = MagicMock()
    mock_transaction.create.side_effect = gcp_exceptions.DeadlineExceeded("Timeout")
    mock_firestore_client.transaction.return_value = mock_transaction
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

    mock_transaction = MagicMock()
    mock_firestore_client.transaction.return_value = mock_transaction
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

    mock_transaction = MagicMock()
    mock_firestore_client.transaction.return_value = mock_transaction
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    create_plan_with_specs(sample_plan_in, mock_firestore_client)

    # Check the plan data stored
    create_calls = mock_transaction.create.call_args_list
    plan_data = create_calls[0][0][1]

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

    mock_transaction = MagicMock()
    mock_firestore_client.transaction.return_value = mock_transaction
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    create_plan_with_specs(sample_plan_in, mock_firestore_client)

    # Verify spec document IDs are strings
    spec_doc_calls = mock_spec_collection.document.call_args_list
    assert len(spec_doc_calls) == 2
    assert spec_doc_calls[0][0][0] == "0"
    assert spec_doc_calls[1][0][0] == "1"


# Tests for execution trigger integration


def test_create_plan_with_specs_sets_execution_metadata_for_spec_0(
    mock_firestore_client, sample_plan_in
):
    """Test that spec 0 gets execution metadata when trigger_first_spec=True."""
    from app.services.firestore_service import create_plan_with_specs

    # Mock plan doesn't exist
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False
    mock_doc_ref.get.return_value = mock_doc_snapshot

    mock_transaction = MagicMock()
    mock_firestore_client.transaction.return_value = mock_transaction
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    create_plan_with_specs(sample_plan_in, mock_firestore_client, trigger_first_spec=True)

    # Check the spec status in transaction.create calls
    create_calls = mock_transaction.create.call_args_list
    assert len(create_calls) == 3  # 1 plan + 2 specs

    # Second call is spec 0 - should have execution metadata set
    spec0_data = create_calls[1][0][1]
    assert spec0_data["status"] == "running"
    assert spec0_data["spec_index"] == 0
    assert spec0_data["execution_attempts"] == 1
    assert spec0_data["last_execution_at"] is not None

    # Third call is spec 1 - should remain blocked with zero attempts
    spec1_data = create_calls[2][0][1]
    assert spec1_data["status"] == "blocked"
    assert spec1_data["spec_index"] == 1
    assert spec1_data["execution_attempts"] == 0
    assert spec1_data["last_execution_at"] is None


def test_create_plan_with_specs_no_execution_metadata_when_flag_false(
    mock_firestore_client, sample_plan_in
):
    """Test that spec 0 doesn't get execution metadata when trigger_first_spec=False."""
    from app.services.firestore_service import create_plan_with_specs

    # Mock plan doesn't exist
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False
    mock_doc_ref.get.return_value = mock_doc_snapshot

    mock_transaction = MagicMock()
    mock_firestore_client.transaction.return_value = mock_transaction
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    create_plan_with_specs(sample_plan_in, mock_firestore_client, trigger_first_spec=False)

    # Check the spec status in transaction.create calls
    create_calls = mock_transaction.create.call_args_list
    assert len(create_calls) == 3  # 1 plan + 2 specs

    # Second call is spec 0 - should NOT have execution metadata set
    spec0_data = create_calls[1][0][1]
    assert spec0_data["status"] == "running"
    assert spec0_data["spec_index"] == 0
    assert spec0_data["execution_attempts"] == 0
    assert spec0_data["last_execution_at"] is None


def test_create_plan_with_multiple_specs_verifies_blocked_status(mock_firestore_client):
    """Test that plans with 3+ specs have only spec 0 running, others blocked with zero attempts."""
    from uuid import uuid4

    from app.models.plan import PlanIn, SpecIn
    from app.services.firestore_service import create_plan_with_specs

    # Create a plan with 3 specs to thoroughly test blocked status
    plan_id = str(uuid4())
    plan_in = PlanIn(
        id=plan_id,
        specs=[
            SpecIn(purpose=f"Purpose {i}", vision=f"Vision {i}", must=[f"req{i}"]) for i in range(3)
        ],
    )

    # Mock plan doesn't exist
    mock_doc_ref = MagicMock()
    mock_doc_snapshot = MagicMock()
    mock_doc_snapshot.exists = False
    mock_doc_ref.get.return_value = mock_doc_snapshot

    mock_transaction = MagicMock()
    mock_firestore_client.transaction.return_value = mock_transaction
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    # Create plan with trigger_first_spec=True
    create_plan_with_specs(plan_in, mock_firestore_client, trigger_first_spec=True)

    # Check the spec status in transaction.create calls
    create_calls = mock_transaction.create.call_args_list
    assert len(create_calls) == 4  # 1 plan + 3 specs

    # Verify spec 0 has execution metadata set
    spec0_data = create_calls[1][0][1]
    assert spec0_data["status"] == "running"
    assert spec0_data["spec_index"] == 0
    assert spec0_data["execution_attempts"] == 1
    assert spec0_data["last_execution_at"] is not None

    # Verify spec 1 is blocked with zero attempts
    spec1_data = create_calls[2][0][1]
    assert spec1_data["status"] == "blocked"
    assert spec1_data["spec_index"] == 1
    assert spec1_data["execution_attempts"] == 0
    assert spec1_data["last_execution_at"] is None

    # Verify spec 2 is blocked with zero attempts
    spec2_data = create_calls[3][0][1]
    assert spec2_data["status"] == "blocked"
    assert spec2_data["spec_index"] == 2
    assert spec2_data["execution_attempts"] == 0
    assert spec2_data["last_execution_at"] is None


def test_delete_plan_with_specs_deletes_plan_and_all_specs(mock_firestore_client, sample_plan_in):
    """Test that delete_plan_with_specs deletes plan and all spec documents."""
    from app.services.firestore_service import delete_plan_with_specs

    # Mock plan and specs
    mock_doc_ref = MagicMock()
    mock_spec_doc_1 = MagicMock()
    mock_spec_doc_2 = MagicMock()
    mock_spec_doc_1.reference = MagicMock()
    mock_spec_doc_2.reference = MagicMock()

    mock_specs_collection = MagicMock()
    mock_specs_collection.stream.return_value = [mock_spec_doc_1, mock_spec_doc_2]
    mock_doc_ref.collection.return_value = mock_specs_collection

    # Mock batch operations
    mock_batch = MagicMock()
    mock_firestore_client.batch.return_value = mock_batch
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    delete_plan_with_specs(sample_plan_in.id, mock_firestore_client)

    # Verify batch.delete was called for both specs and the plan
    assert mock_batch.delete.call_count == 3  # 2 specs + 1 plan
    # First two deletes are for specs
    mock_batch.delete.assert_any_call(mock_spec_doc_1.reference)
    mock_batch.delete.assert_any_call(mock_spec_doc_2.reference)
    # Last delete is for plan
    mock_batch.delete.assert_any_call(mock_doc_ref)
    # Verify batch was committed
    mock_batch.commit.assert_called_once()


def test_delete_plan_with_specs_handles_empty_specs(mock_firestore_client):
    """Test that delete_plan_with_specs handles plans with no specs."""
    from app.services.firestore_service import delete_plan_with_specs

    plan_id = "test-plan-id"
    mock_doc_ref = MagicMock()
    mock_specs_collection = MagicMock()
    mock_specs_collection.stream.return_value = []  # No specs
    mock_doc_ref.collection.return_value = mock_specs_collection

    # Mock batch operations
    mock_batch = MagicMock()
    mock_firestore_client.batch.return_value = mock_batch
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    delete_plan_with_specs(plan_id, mock_firestore_client)

    # Only plan should be deleted
    assert mock_batch.delete.call_count == 1
    mock_batch.delete.assert_called_with(mock_doc_ref)
    mock_batch.commit.assert_called_once()


def test_delete_plan_with_specs_handles_firestore_errors(mock_firestore_client):
    """Test that delete_plan_with_specs handles Firestore errors."""
    from app.services.firestore_service import FirestoreOperationError, delete_plan_with_specs

    plan_id = "test-plan-id"
    mock_doc_ref = MagicMock()
    mock_specs_collection = MagicMock()
    mock_specs_collection.stream.side_effect = gcp_exceptions.DeadlineExceeded("Timeout")
    mock_doc_ref.collection.return_value = mock_specs_collection

    mock_transaction = MagicMock()
    mock_firestore_client.transaction.return_value = mock_transaction
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with pytest.raises(FirestoreOperationError) as exc_info:
        delete_plan_with_specs(plan_id, mock_firestore_client)

    assert "Firestore API error" in str(exc_info.value)


def test_delete_plan_with_specs_uses_default_client_when_none_provided(
    mock_settings, mock_firestore_client
):
    """Test that delete_plan_with_specs uses get_client() when client not provided."""
    from app.services.firestore_service import delete_plan_with_specs

    plan_id = "test-plan-id"
    mock_doc_ref = MagicMock()
    mock_specs_collection = MagicMock()
    mock_specs_collection.stream.return_value = []
    mock_doc_ref.collection.return_value = mock_specs_collection

    # Mock batch operations
    mock_batch = MagicMock()
    mock_firestore_client.batch.return_value = mock_batch
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    # Call without client parameter
    delete_plan_with_specs(plan_id)

    # Should use cached client
    assert mock_batch.delete.called


def test_delete_plan_with_specs_logs_deletion(mock_firestore_client, caplog):
    """Test that delete_plan_with_specs logs successful deletion."""
    from app.services.firestore_service import delete_plan_with_specs

    plan_id = "test-plan-id"
    mock_doc_ref = MagicMock()
    mock_specs_collection = MagicMock()
    mock_specs_collection.stream.return_value = []
    mock_doc_ref.collection.return_value = mock_specs_collection

    # Mock batch operations
    mock_batch = MagicMock()
    mock_firestore_client.batch.return_value = mock_batch
    mock_firestore_client.collection.return_value.document.return_value = mock_doc_ref

    with caplog.at_level(logging.INFO):
        delete_plan_with_specs(plan_id, mock_firestore_client)

    info_messages = [record.message for record in caplog.records if record.levelname == "INFO"]
    assert any("Deleted plan" in msg and plan_id in msg for msg in info_messages)


# Tests for process_spec_status_update functionality


@pytest.fixture
def mock_transaction_client():
    """Create a mock Firestore client for transaction testing."""
    mock_client = MagicMock()
    mock_transaction = MagicMock()
    mock_client.transaction.return_value = mock_transaction
    return mock_client


def test_process_spec_status_update_finishing_last_spec(mock_transaction_client):
    """Test finishing last spec marks plan finished and sets current_spec_index to null."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-123"

    # Mock plan document - single spec plan
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "running",
        "total_specs": 1,
        "completed_specs": 0,
        "current_spec_index": 0,
    }

    # Mock spec document
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = True
    mock_spec_snapshot.to_dict.return_value = {
        "status": "running",
        "history": [],
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()

    # Setup get calls to return plan snapshot then spec snapshot
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get.return_value = mock_spec_snapshot
    mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="finished",
        stage="implementation",
        message_id=message_id,
        raw_payload_snippet={"test": "data"},
        client=mock_transaction_client,
    )

    assert result["success"] is True
    assert result["plan_finished"] is True
    assert result["next_spec_triggered"] is False

    # Verify plan was updated with overall_status=finished and current_spec_index=None
    transaction = mock_transaction_client.transaction.return_value
    update_calls = list(transaction.update.call_args_list)
    assert len(update_calls) == 2  # spec update + plan update

    # Check plan update
    plan_update_call = update_calls[1]
    plan_updates = plan_update_call[0][1]
    assert plan_updates["overall_status"] == "finished"
    assert plan_updates["current_spec_index"] is None
    assert plan_updates["completed_specs"] == 1


def test_process_spec_status_update_finishing_non_last_spec(mock_transaction_client):
    """Test that finishing a non-last spec advances to next spec and triggers execution."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-123"

    # Mock plan document - 2 spec plan
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "running",
        "total_specs": 2,
        "completed_specs": 0,
        "current_spec_index": 0,
    }

    # Mock current spec document
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = True
    mock_spec_snapshot.to_dict.return_value = {
        "status": "running",
        "history": [],
    }

    # Mock next spec document (blocked)
    mock_next_spec_snapshot = MagicMock()
    mock_next_spec_snapshot.exists = True
    mock_next_spec_snapshot.to_dict.return_value = {
        "status": "blocked",
        "history": [],
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()
    mock_next_spec_ref = MagicMock()

    # Setup get calls to return snapshots in order
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get.return_value = mock_spec_snapshot
    mock_next_spec_ref.get.return_value = mock_next_spec_snapshot

    mock_specs_collection = MagicMock()

    def document_side_effect(doc_id):
        if doc_id == "0":
            return mock_spec_ref
        elif doc_id == "1":
            return mock_next_spec_ref
        return MagicMock()

    mock_specs_collection.document = document_side_effect
    mock_plan_ref.collection.return_value = mock_specs_collection

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="finished",
        stage="implementation",
        message_id=message_id,
        raw_payload_snippet={"test": "data"},
        client=mock_transaction_client,
    )

    # Verify the result indicates execution should be triggered
    assert result["success"] is True
    assert result["plan_finished"] is False
    assert result["next_spec_triggered"] is True
    assert "spec 1 unblocked" in result["message"].lower()

    # Verify next spec was unblocked (status changed to running)
    transaction = mock_transaction_client.transaction.return_value
    update_calls = list(transaction.update.call_args_list)
    assert len(update_calls) == 3  # next spec + current spec + plan

    # Check updates were made (order: next spec, current spec, plan)
    # First update is next spec (running)
    next_spec_update_call = update_calls[0]
    next_spec_updates = next_spec_update_call[0][1]
    assert next_spec_updates["status"] == "running"

    # Second update is current spec (finished)
    spec_update_call = update_calls[1]
    spec_updates = spec_update_call[0][1]
    assert spec_updates["status"] == "finished"

    # Third update is plan (next spec is now current)
    plan_update_call = update_calls[2]
    plan_updates = plan_update_call[0][1]
    assert plan_updates["current_spec_index"] == 1
    assert plan_updates["completed_specs"] == 1


def test_process_spec_status_update_failed_spec(mock_transaction_client):
    """Test that failed spec marks both spec and plan as failed, never calls ExecutionService."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-123"

    # Mock plan document - 2 spec plan
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "running",
        "total_specs": 2,
        "completed_specs": 0,
        "current_spec_index": 0,
    }

    # Mock spec document
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = True
    mock_spec_snapshot.to_dict.return_value = {
        "status": "running",
        "history": [],
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()

    # Setup get calls to return snapshots in order
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get = MagicMock(return_value=mock_spec_snapshot)
    mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="failed",
        stage="implementation",
        message_id=message_id,
        raw_payload_snippet={"test": "data"},
        client=mock_transaction_client,
    )

    assert result["success"] is True
    assert result["plan_finished"] is False
    assert result["next_spec_triggered"] is False

    # Verify spec was marked as failed
    transaction = mock_transaction_client.transaction.return_value
    update_calls = list(transaction.update.call_args_list)
    assert len(update_calls) == 2  # spec update + plan update

    # Check spec update
    spec_update_call = update_calls[0]
    spec_updates = spec_update_call[0][1]
    assert spec_updates["status"] == "failed"

    # Check plan update
    plan_update_call = update_calls[1]
    plan_updates = plan_update_call[0][1]
    assert plan_updates["overall_status"] == "failed"


def test_process_spec_status_update_intermediate_status(mock_transaction_client):
    """Test intermediate status updates only stage field while leaving primary status untouched."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-123"

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "running",
        "total_specs": 2,
        "completed_specs": 0,
        "current_spec_index": 0,
    }

    # Mock spec document
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = True
    mock_spec_snapshot.to_dict.return_value = {
        "status": "running",
        "history": [],
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()

    # Setup get calls to return snapshots in order
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get = MagicMock(return_value=mock_spec_snapshot)
    mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="running",  # Non-terminal status
        stage="reviewing",  # Intermediate stage
        message_id=message_id,
        raw_payload_snippet={"test": "data"},
        client=mock_transaction_client,
    )

    assert result["success"] is True
    assert result["plan_finished"] is False
    assert result["next_spec_triggered"] is False

    # Verify only stage was updated, not status
    transaction = mock_transaction_client.transaction.return_value
    update_calls = list(transaction.update.call_args_list)
    assert len(update_calls) == 2  # spec update + plan update

    # Check spec update
    spec_update_call = update_calls[0]
    spec_updates = spec_update_call[0][1]
    assert "status" not in spec_updates  # status should NOT be changed
    assert spec_updates["current_stage"] == "reviewing"
    assert len(spec_updates["history"]) == 1


def test_process_spec_status_update_out_of_order_finished(mock_transaction_client):
    """Test that out-of-order finished message aborts transaction and logs error."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 1  # Trying to finish spec 1
    message_id = "msg-123"

    # Mock plan document - current spec is 0, not 1
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "running",
        "total_specs": 3,
        "completed_specs": 0,
        "current_spec_index": 0,  # Current spec is 0, not 1
    }

    # Mock spec document
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = True
    mock_spec_snapshot.to_dict.return_value = {
        "status": "blocked",
        "history": [],
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()

    # Setup get calls to return snapshots in order
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get = MagicMock(return_value=mock_spec_snapshot)
    mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="finished",
        stage="implementation",
        message_id=message_id,
        raw_payload_snippet={"test": "data"},
        client=mock_transaction_client,
    )

    assert result["success"] is False
    assert result["action"] == "out_of_order"
    assert "out of order" in result["message"].lower()

    # Verify NO updates were made
    transaction = mock_transaction_client.transaction.return_value
    transaction.update.assert_not_called()


def test_process_spec_status_update_duplicate_message_id(mock_transaction_client):
    """Test that duplicate messageIds are filtered from history and don't re-trigger execution."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-123"

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "running",
        "total_specs": 2,
        "completed_specs": 0,
        "current_spec_index": 0,
    }

    # Mock spec document with message_id already in history
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = True
    mock_spec_snapshot.to_dict.return_value = {
        "status": "running",
        "history": [
            {
                "timestamp": "2025-01-01T12:00:00Z",
                "received_status": "running",
                "stage": "implementation",
                "message_id": "msg-123",  # Duplicate message
            }
        ],
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()

    # Setup get calls to return snapshots in order
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get = MagicMock(return_value=mock_spec_snapshot)
    mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="finished",
        stage="implementation",
        message_id=message_id,
        raw_payload_snippet={"test": "data"},
        client=mock_transaction_client,
    )

    assert result["success"] is True
    assert result["action"] == "duplicate"
    assert "duplicate" in result["message"].lower()

    # Verify NO updates were made
    transaction = mock_transaction_client.transaction.return_value
    transaction.update.assert_not_called()


def test_process_spec_status_update_history_entry_contents(mock_transaction_client):
    """Test that history entries contain timestamp, stage, messageId, and raw snippet."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-123"
    raw_snippet = {"plan_id": plan_id, "spec_index": spec_index, "status": "running"}

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "running",
        "total_specs": 2,
        "completed_specs": 0,
        "current_spec_index": 0,
    }

    # Mock spec document
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = True
    mock_spec_snapshot.to_dict.return_value = {
        "status": "running",
        "history": [],
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()

    # Setup get calls to return snapshots in order
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get = MagicMock(return_value=mock_spec_snapshot)
    mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="running",
        stage="reviewing",
        message_id=message_id,
        raw_payload_snippet=raw_snippet,
        client=mock_transaction_client,
    )

    assert result["success"] is True

    # Verify history entry contents
    transaction = mock_transaction_client.transaction.return_value
    update_calls = list(transaction.update.call_args_list)
    spec_update_call = update_calls[0]
    spec_updates = spec_update_call[0][1]

    history = spec_updates["history"]
    assert len(history) == 1
    history_entry = history[0]
    assert "timestamp" in history_entry
    assert history_entry["received_status"] == "running"
    assert history_entry["stage"] == "reviewing"
    assert history_entry["message_id"] == message_id
    assert history_entry["raw_snippet"] == raw_snippet


def test_process_spec_status_update_manual_retry_after_failure(mock_transaction_client):
    """Test that previously failed spec can record new non-terminal events without unblocking."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-retry-123"

    # Mock plan document - plan is failed
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "failed",
        "total_specs": 2,
        "completed_specs": 0,
        "current_spec_index": 0,
    }

    # Mock spec document - spec is failed
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = True
    mock_spec_snapshot.to_dict.return_value = {
        "status": "failed",
        "history": [
            {
                "timestamp": "2025-01-01T12:00:00Z",
                "received_status": "failed",
                "stage": "implementation",
                "message_id": "msg-original-fail",
            }
        ],
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()

    # Setup get calls to return snapshots in order
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get = MagicMock(return_value=mock_spec_snapshot)
    mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    # Send a non-terminal status (manual retry)
    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="running",  # Non-terminal status
        stage="retrying",
        message_id=message_id,
        raw_payload_snippet={"test": "retry"},
        client=mock_transaction_client,
    )

    # Should be accepted but NOT change terminal status or unblock next spec
    assert result["success"] is True
    assert result["next_spec_triggered"] is False

    # Verify history was appended but status remains terminal
    transaction = mock_transaction_client.transaction.return_value
    update_calls = list(transaction.update.call_args_list)
    spec_update_call = update_calls[0]
    spec_updates = spec_update_call[0][1]

    # Status should NOT be in the update (terminal status preserved)
    assert "status" not in spec_updates
    # History should have new entry
    assert len(spec_updates["history"]) == 2
    assert spec_updates["history"][1]["message_id"] == message_id


def test_process_spec_status_update_terminal_status_protection(mock_transaction_client):
    """Test that duplicate terminal statuses are prevented."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-duplicate-finished"

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "running",
        "total_specs": 2,
        "completed_specs": 0,
        "current_spec_index": 0,
    }

    # Mock spec document - already finished
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = True
    mock_spec_snapshot.to_dict.return_value = {
        "status": "finished",  # Already terminal
        "history": [
            {
                "timestamp": "2025-01-01T12:00:00Z",
                "received_status": "finished",
                "stage": "implementation",
                "message_id": "msg-original-finished",
            }
        ],
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()

    # Setup get calls to return snapshots in order
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get = MagicMock(return_value=mock_spec_snapshot)
    mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    # Try to finish again
    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="finished",  # Duplicate terminal status
        stage="implementation",
        message_id=message_id,
        raw_payload_snippet={"test": "duplicate"},
        client=mock_transaction_client,
    )

    assert result["success"] is False
    assert result["action"] == "out_of_order"
    assert "terminal" in result["message"].lower()

    # Verify NO updates were made
    transaction = mock_transaction_client.transaction.return_value
    transaction.update.assert_not_called()


def test_process_spec_status_update_plan_not_found(mock_transaction_client):
    """Test that missing plan returns not_found and doesn't fail."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "missing-plan-id"
    spec_index = 0
    message_id = "msg-123"

    # Mock plan document - doesn't exist
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = False

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_plan_ref.get = MagicMock(return_value=mock_plan_snapshot)

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="finished",
        stage="implementation",
        message_id=message_id,
        raw_payload_snippet={"test": "data"},
        client=mock_transaction_client,
    )

    assert result["success"] is False
    assert result["action"] == "not_found"
    assert "not found" in result["message"].lower()

    # Verify NO updates were made
    transaction = mock_transaction_client.transaction.return_value
    transaction.update.assert_not_called()


def test_process_spec_status_update_spec_not_found(mock_transaction_client):
    """Test that missing spec returns not_found and doesn't fail."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 99  # Non-existent spec
    message_id = "msg-123"

    # Mock plan document - exists
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "running",
        "total_specs": 2,
        "completed_specs": 0,
        "current_spec_index": 0,
    }

    # Mock spec document - doesn't exist
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = False

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()

    # Setup get calls to return snapshots in order
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get = MagicMock(return_value=mock_spec_snapshot)
    mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="finished",
        stage="implementation",
        message_id=message_id,
        raw_payload_snippet={"test": "data"},
        client=mock_transaction_client,
    )

    assert result["success"] is False
    assert result["action"] == "not_found"
    assert "not found" in result["message"].lower()

    # Verify NO updates were made
    transaction = mock_transaction_client.transaction.return_value
    transaction.update.assert_not_called()


def test_process_spec_status_update_with_null_stage(mock_transaction_client):
    """Test that null/None stage values are handled correctly."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-123"

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "running",
        "total_specs": 2,
        "completed_specs": 0,
        "current_spec_index": 0,
    }

    # Mock spec document
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = True
    mock_spec_snapshot.to_dict.return_value = {
        "status": "running",
        "history": [],
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()

    # Setup get calls to return snapshots in order
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get = MagicMock(return_value=mock_spec_snapshot)
    mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="running",
        stage=None,  # Null stage
        message_id=message_id,
        raw_payload_snippet={"test": "data"},
        client=mock_transaction_client,
    )

    assert result["success"] is True

    # Verify history entry has None stage
    transaction = mock_transaction_client.transaction.return_value
    update_calls = list(transaction.update.call_args_list)
    spec_update_call = update_calls[0]
    spec_updates = spec_update_call[0][1]

    history = spec_updates["history"]
    assert len(history) == 1
    assert history[0]["stage"] is None


def test_process_spec_status_update_with_large_payload(mock_transaction_client):
    """Test that large raw_payload_snippets are handled correctly."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-123"

    # Create a large payload snippet
    large_payload = {
        "plan_id": plan_id,
        "spec_index": spec_index,
        "status": "running",
        "large_field": "x" * 10000,  # 10KB of data
        "nested": {"data": ["item"] * 1000},
    }

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "running",
        "total_specs": 2,
        "completed_specs": 0,
        "current_spec_index": 0,
    }

    # Mock spec document
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = True
    mock_spec_snapshot.to_dict.return_value = {
        "status": "running",
        "history": [],
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()

    # Setup get calls to return snapshots in order
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get = MagicMock(return_value=mock_spec_snapshot)
    mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="running",
        stage="implementation",
        message_id=message_id,
        raw_payload_snippet=large_payload,
        client=mock_transaction_client,
    )

    assert result["success"] is True

    # Verify large payload was stored in history
    transaction = mock_transaction_client.transaction.return_value
    update_calls = list(transaction.update.call_args_list)
    spec_update_call = update_calls[0]
    spec_updates = spec_update_call[0][1]

    history = spec_updates["history"]
    assert len(history) == 1
    assert history[0]["raw_snippet"] == large_payload
    assert len(history[0]["raw_snippet"]["large_field"]) == 10000


def test_process_spec_status_update_with_special_char_message_id(mock_transaction_client):
    """Test that special characters in messageId are handled correctly."""
    from app.services.firestore_service import process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    # MessageId with special characters
    message_id = "msg-123_@#$%^&*()[]{}|\\:;\"'<>,.?/~`"

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "overall_status": "running",
        "total_specs": 2,
        "completed_specs": 0,
        "current_spec_index": 0,
    }

    # Mock spec document
    mock_spec_snapshot = MagicMock()
    mock_spec_snapshot.exists = True
    mock_spec_snapshot.to_dict.return_value = {
        "status": "running",
        "history": [],
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_spec_ref = MagicMock()

    # Setup get calls to return snapshots in order
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_spec_ref.get = MagicMock(return_value=mock_spec_snapshot)
    mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    result = process_spec_status_update(
        plan_id=plan_id,
        spec_index=spec_index,
        status="running",
        stage="implementation",
        message_id=message_id,
        raw_payload_snippet={"test": "data"},
        client=mock_transaction_client,
    )

    assert result["success"] is True

    # Verify special char messageId was stored correctly
    transaction = mock_transaction_client.transaction.return_value
    update_calls = list(transaction.update.call_args_list)
    spec_update_call = update_calls[0]
    spec_updates = spec_update_call[0][1]

    history = spec_updates["history"]
    assert len(history) == 1
    assert history[0]["message_id"] == message_id


def test_process_spec_status_update_firestore_deadline_exceeded(mock_transaction_client):
    """Test that DeadlineExceeded errors are properly wrapped."""
    from app.services.firestore_service import FirestoreOperationError, process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-123"

    # Mock plan ref to raise Firestore error
    mock_plan_ref = MagicMock()
    mock_plan_ref.get.side_effect = gcp_exceptions.DeadlineExceeded("Timeout")

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    with pytest.raises(FirestoreOperationError) as exc_info:
        process_spec_status_update(
            plan_id=plan_id,
            spec_index=spec_index,
            status="finished",
            stage="implementation",
            message_id=message_id,
            raw_payload_snippet={"test": "data"},
            client=mock_transaction_client,
        )

    assert "Firestore API error" in str(exc_info.value)
    assert plan_id in str(exc_info.value)


def test_process_spec_status_update_firestore_aborted(mock_transaction_client):
    """Test that Aborted errors (transaction conflicts) are properly wrapped."""
    from app.services.firestore_service import FirestoreOperationError, process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-123"

    # Mock plan ref to raise Aborted error (common in high-contention scenarios)
    mock_plan_ref = MagicMock()
    mock_plan_ref.get.side_effect = gcp_exceptions.Aborted("Transaction aborted")

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    with pytest.raises(FirestoreOperationError) as exc_info:
        process_spec_status_update(
            plan_id=plan_id,
            spec_index=spec_index,
            status="finished",
            stage="implementation",
            message_id=message_id,
            raw_payload_snippet={"test": "data"},
            client=mock_transaction_client,
        )

    assert "Firestore API error" in str(exc_info.value)
    assert plan_id in str(exc_info.value)


def test_process_spec_status_update_firestore_failed_precondition(mock_transaction_client):
    """Test that FailedPrecondition errors are properly wrapped."""
    from app.services.firestore_service import FirestoreOperationError, process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-123"

    # Mock plan ref to raise FailedPrecondition error
    mock_plan_ref = MagicMock()
    mock_plan_ref.get.side_effect = gcp_exceptions.FailedPrecondition("Precondition failed")

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    with pytest.raises(FirestoreOperationError) as exc_info:
        process_spec_status_update(
            plan_id=plan_id,
            spec_index=spec_index,
            status="finished",
            stage="implementation",
            message_id=message_id,
            raw_payload_snippet={"test": "data"},
            client=mock_transaction_client,
        )

    assert "Firestore API error" in str(exc_info.value)
    assert plan_id in str(exc_info.value)


def test_process_spec_status_update_firestore_resource_exhausted(mock_transaction_client):
    """Test that ResourceExhausted errors (quota limits) are properly wrapped."""
    from app.services.firestore_service import FirestoreOperationError, process_spec_status_update

    plan_id = "test-plan-id"
    spec_index = 0
    message_id = "msg-123"

    # Mock plan ref to raise ResourceExhausted error
    mock_plan_ref = MagicMock()
    mock_plan_ref.get.side_effect = gcp_exceptions.ResourceExhausted("Quota exceeded")

    mock_transaction_client.collection.return_value.document.return_value = mock_plan_ref

    with pytest.raises(FirestoreOperationError) as exc_info:
        process_spec_status_update(
            plan_id=plan_id,
            spec_index=spec_index,
            status="finished",
            stage="implementation",
            message_id=message_id,
            raw_payload_snippet={"test": "data"},
            client=mock_transaction_client,
        )

    assert "Firestore API error" in str(exc_info.value)
    assert plan_id in str(exc_info.value)


# Tests for get_plan_with_specs functionality


def test_get_plan_with_specs_returns_plan_and_specs(mock_firestore_client):
    """Test that get_plan_with_specs returns plan data and spec list."""
    from datetime import UTC, datetime

    from app.services.firestore_service import get_plan_with_specs

    plan_id = "test-plan-id"
    now = datetime.now(UTC)

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "plan_id": plan_id,
        "overall_status": "running",
        "created_at": now,
        "updated_at": now,
        "total_specs": 2,
        "completed_specs": 1,
        "current_spec_index": 1,
        "last_event_at": now,
        "raw_request": {},
    }

    # Mock spec documents
    mock_spec_doc_1 = MagicMock()
    mock_spec_doc_1.to_dict.return_value = {
        "spec_index": 0,
        "purpose": "Spec 0",
        "vision": "Vision 0",
        "status": "finished",
        "created_at": now,
        "updated_at": now,
    }

    mock_spec_doc_2 = MagicMock()
    mock_spec_doc_2.to_dict.return_value = {
        "spec_index": 1,
        "purpose": "Spec 1",
        "vision": "Vision 1",
        "status": "running",
        "created_at": now,
        "updated_at": now,
    }

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_plan_ref.get.return_value = mock_plan_snapshot

    mock_specs_query = MagicMock()
    mock_specs_query.stream.return_value = [mock_spec_doc_1, mock_spec_doc_2]

    mock_specs_ref = MagicMock()
    mock_specs_ref.order_by.return_value = mock_specs_query

    mock_plan_ref.collection.return_value = mock_specs_ref
    mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

    plan_data, spec_list = get_plan_with_specs(plan_id, mock_firestore_client)

    assert plan_data is not None
    assert plan_data["plan_id"] == plan_id
    assert len(spec_list) == 2
    assert spec_list[0]["spec_index"] == 0
    assert spec_list[1]["spec_index"] == 1


def test_get_plan_with_specs_uses_single_ordered_query(mock_firestore_client):
    """Test that get_plan_with_specs uses a single query ordered by spec_index."""
    from datetime import UTC, datetime

    from app.services.firestore_service import get_plan_with_specs

    plan_id = "test-plan-id"
    now = datetime.now(UTC)

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "plan_id": plan_id,
        "overall_status": "running",
        "created_at": now,
        "updated_at": now,
        "total_specs": 3,
        "last_event_at": now,
        "raw_request": {},
    }

    # Mock spec documents
    mock_spec_docs = [
        MagicMock(
            to_dict=lambda i=i: {
                "spec_index": i,
                "purpose": f"Spec {i}",
                "vision": f"Vision {i}",
                "status": "blocked",
                "created_at": now,
                "updated_at": now,
            }
        )
        for i in range(3)
    ]

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_plan_ref.get.return_value = mock_plan_snapshot

    mock_specs_query = MagicMock()
    mock_specs_query.stream.return_value = mock_spec_docs

    mock_specs_ref = MagicMock()
    mock_specs_ref.order_by.return_value = mock_specs_query

    mock_plan_ref.collection.return_value = mock_specs_ref
    mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

    # Import firestore.Query to verify direction constant
    from google.cloud import firestore

    get_plan_with_specs(plan_id, mock_firestore_client)

    # Verify single query was made with correct ordering
    mock_specs_ref.order_by.assert_called_once_with(
        "spec_index", direction=firestore.Query.ASCENDING
    )
    mock_specs_query.stream.assert_called_once()


def test_get_plan_with_specs_returns_none_for_missing_plan(mock_firestore_client):
    """Test that get_plan_with_specs returns None for non-existent plan."""
    from app.services.firestore_service import get_plan_with_specs

    plan_id = "missing-plan-id"

    # Mock plan document - doesn't exist
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = False

    mock_plan_ref = MagicMock()
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

    plan_data, spec_list = get_plan_with_specs(plan_id, mock_firestore_client)

    assert plan_data is None
    assert spec_list == []


def test_get_plan_with_specs_handles_empty_specs(mock_firestore_client):
    """Test that get_plan_with_specs handles plans with no specs."""
    from datetime import UTC, datetime

    from app.services.firestore_service import get_plan_with_specs

    plan_id = "test-plan-id"
    now = datetime.now(UTC)

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "plan_id": plan_id,
        "overall_status": "running",
        "created_at": now,
        "updated_at": now,
        "total_specs": 0,
        "last_event_at": now,
        "raw_request": {},
    }

    # Mock empty specs query
    mock_specs_query = MagicMock()
    mock_specs_query.stream.return_value = []

    mock_specs_ref = MagicMock()
    mock_specs_ref.order_by.return_value = mock_specs_query

    mock_plan_ref = MagicMock()
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_plan_ref.collection.return_value = mock_specs_ref
    mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

    plan_data, spec_list = get_plan_with_specs(plan_id, mock_firestore_client)

    assert plan_data is not None
    assert spec_list == []


def test_get_plan_with_specs_filters_empty_spec_documents(mock_firestore_client):
    """Test that get_plan_with_specs filters out empty spec documents."""
    from datetime import UTC, datetime

    from app.services.firestore_service import get_plan_with_specs

    plan_id = "test-plan-id"
    now = datetime.now(UTC)

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "plan_id": plan_id,
        "overall_status": "running",
        "created_at": now,
        "updated_at": now,
        "total_specs": 2,
        "last_event_at": now,
        "raw_request": {},
    }

    # Mock spec documents - one valid, one empty
    mock_spec_doc_1 = MagicMock()
    mock_spec_doc_1.to_dict.return_value = {
        "spec_index": 0,
        "purpose": "Spec 0",
        "vision": "Vision 0",
        "status": "blocked",
        "created_at": now,
        "updated_at": now,
    }

    mock_spec_doc_2 = MagicMock()
    mock_spec_doc_2.to_dict.return_value = None  # Empty document

    # Setup mock references
    mock_plan_ref = MagicMock()
    mock_plan_ref.get.return_value = mock_plan_snapshot

    mock_specs_query = MagicMock()
    mock_specs_query.stream.return_value = [mock_spec_doc_1, mock_spec_doc_2]

    mock_specs_ref = MagicMock()
    mock_specs_ref.order_by.return_value = mock_specs_query

    mock_plan_ref.collection.return_value = mock_specs_ref
    mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

    plan_data, spec_list = get_plan_with_specs(plan_id, mock_firestore_client)

    assert plan_data is not None
    # Should only include the valid spec document
    assert len(spec_list) == 1
    assert spec_list[0]["spec_index"] == 0


def test_get_plan_with_specs_raises_error_for_empty_plan_document(mock_firestore_client):
    """Test that get_plan_with_specs raises error for empty plan document."""
    from app.services.firestore_service import FirestoreOperationError, get_plan_with_specs

    plan_id = "test-plan-id"

    # Mock plan document - exists but is empty
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = None  # Empty document

    mock_plan_ref = MagicMock()
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

    with pytest.raises(FirestoreOperationError) as exc_info:
        get_plan_with_specs(plan_id, mock_firestore_client)

    assert "exists but is empty" in str(exc_info.value)


def test_get_plan_with_specs_handles_firestore_errors(mock_firestore_client):
    """Test that get_plan_with_specs handles Firestore API errors."""
    from app.services.firestore_service import FirestoreOperationError, get_plan_with_specs

    plan_id = "test-plan-id"

    # Mock plan ref to raise Firestore error
    mock_plan_ref = MagicMock()
    mock_plan_ref.get.side_effect = gcp_exceptions.DeadlineExceeded("Timeout")

    mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

    with pytest.raises(FirestoreOperationError) as exc_info:
        get_plan_with_specs(plan_id, mock_firestore_client)

    assert "Firestore API error" in str(exc_info.value)
    assert plan_id in str(exc_info.value)


def test_get_plan_with_specs_uses_default_client_when_none_provided(
    mock_settings, mock_firestore_client
):
    """Test that get_plan_with_specs uses get_client() when client not provided."""
    from datetime import UTC, datetime

    from app.services.firestore_service import get_plan_with_specs

    plan_id = "test-plan-id"
    now = datetime.now(UTC)

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "plan_id": plan_id,
        "overall_status": "running",
        "created_at": now,
        "updated_at": now,
        "total_specs": 0,
        "last_event_at": now,
        "raw_request": {},
    }

    mock_specs_query = MagicMock()
    mock_specs_query.stream.return_value = []

    mock_specs_ref = MagicMock()
    mock_specs_ref.order_by.return_value = mock_specs_query

    mock_plan_ref = MagicMock()
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_plan_ref.collection.return_value = mock_specs_ref
    mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

    # Call without client parameter
    plan_data, spec_list = get_plan_with_specs(plan_id)

    assert plan_data is not None
    assert spec_list == []


def test_get_plan_with_specs_logs_successful_fetch(mock_firestore_client, caplog):
    """Test that get_plan_with_specs logs successful fetches."""
    from datetime import UTC, datetime

    from app.services.firestore_service import get_plan_with_specs

    plan_id = "test-plan-id"
    now = datetime.now(UTC)

    # Mock plan document
    mock_plan_snapshot = MagicMock()
    mock_plan_snapshot.exists = True
    mock_plan_snapshot.to_dict.return_value = {
        "plan_id": plan_id,
        "overall_status": "running",
        "created_at": now,
        "updated_at": now,
        "total_specs": 2,
        "last_event_at": now,
        "raw_request": {},
    }

    mock_spec_doc_1 = MagicMock()
    mock_spec_doc_1.to_dict.return_value = {
        "spec_index": 0,
        "purpose": "Spec 0",
        "vision": "Vision 0",
        "status": "blocked",
        "created_at": now,
        "updated_at": now,
    }

    mock_spec_doc_2 = MagicMock()
    mock_spec_doc_2.to_dict.return_value = {
        "spec_index": 1,
        "purpose": "Spec 1",
        "vision": "Vision 1",
        "status": "blocked",
        "created_at": now,
        "updated_at": now,
    }

    mock_specs_query = MagicMock()
    mock_specs_query.stream.return_value = [mock_spec_doc_1, mock_spec_doc_2]

    mock_specs_ref = MagicMock()
    mock_specs_ref.order_by.return_value = mock_specs_query

    mock_plan_ref = MagicMock()
    mock_plan_ref.get.return_value = mock_plan_snapshot
    mock_plan_ref.collection.return_value = mock_specs_ref
    mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

    with caplog.at_level(logging.INFO):
        get_plan_with_specs(plan_id, mock_firestore_client)

    info_messages = [record.message for record in caplog.records if record.levelname == "INFO"]
    assert any("Fetched plan" in msg and plan_id in msg for msg in info_messages)
    assert any("2 specs" in msg for msg in info_messages)
