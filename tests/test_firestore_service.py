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
