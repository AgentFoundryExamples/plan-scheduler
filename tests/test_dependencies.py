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
"""Tests for dependency injection orchestration logic."""

import logging
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.dependencies import create_plan
from app.models.plan import PlanIn, SpecIn, SpecRecord
from app.services.firestore_service import (
    FirestoreOperationError,
    PlanConflictError,
    PlanIngestionOutcome,
)


@pytest.fixture
def valid_plan_in():
    """Create a valid PlanIn for testing."""
    return PlanIn(
        id=str(uuid.uuid4()),
        specs=[
            SpecIn(
                purpose="Test purpose 1",
                vision="Test vision 1",
                must=["must1"],
                dont=["dont1"],
                nice=["nice1"],
                assumptions=["assumption1"],
            ),
            SpecIn(
                purpose="Test purpose 2",
                vision="Test vision 2",
                must=["must2"],
                dont=["dont2"],
                nice=["nice2"],
                assumptions=["assumption2"],
            ),
        ],
    )


@pytest.fixture
def mock_spec_record():
    """Create a mock SpecRecord."""
    return SpecRecord(
        spec_index=0,
        purpose="Test purpose",
        vision="Test vision",
        must=["must1"],
        dont=["dont1"],
        nice=["nice1"],
        assumptions=["assumption1"],
        status="running",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        execution_attempts=1,
        last_execution_at=datetime.now(UTC),
        history=[],
    )


def test_create_plan_success_with_execution_enabled(valid_plan_in, mock_spec_record):
    """Test create_plan successfully creates plan and triggers execution when enabled."""
    with patch("app.dependencies.get_cached_settings") as mock_settings, patch(
        "app.dependencies.get_execution_service"
    ) as mock_exec_service, patch("app.dependencies.get_firestore_client") as mock_client, patch(
        "app.dependencies.firestore_service.create_plan_with_specs"
    ) as mock_create:
        # Setup mocks
        settings = MagicMock()
        settings.EXECUTION_ENABLED = True
        mock_settings.return_value = settings

        exec_service = MagicMock()
        mock_exec_service.return_value = exec_service

        client = MagicMock()
        spec_doc_snapshot = MagicMock()
        spec_doc_snapshot.exists = True
        spec_doc_snapshot.to_dict.return_value = mock_spec_record.model_dump()
        client.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
            spec_doc_snapshot
        )
        mock_client.return_value = client

        mock_create.return_value = (PlanIngestionOutcome.CREATED, valid_plan_in.id)

        # Call create_plan
        outcome, plan_id = create_plan(valid_plan_in)

        # Verify outcome
        assert outcome == PlanIngestionOutcome.CREATED
        assert plan_id == valid_plan_in.id

        # Verify create_plan_with_specs was called with trigger_first_spec=True
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["trigger_first_spec"] is True

        # Verify execution trigger was called
        exec_service.trigger_spec_execution.assert_called_once()
        call_args = exec_service.trigger_spec_execution.call_args
        assert call_args[1]["plan_id"] == valid_plan_in.id
        assert call_args[1]["spec_index"] == 0


def test_create_plan_success_with_execution_disabled(valid_plan_in):
    """Test create_plan succeeds without triggering execution when disabled."""
    with patch("app.dependencies.get_cached_settings") as mock_settings, patch(
        "app.dependencies.get_execution_service"
    ) as mock_exec_service, patch("app.dependencies.get_firestore_client") as mock_client, patch(
        "app.dependencies.firestore_service.create_plan_with_specs"
    ) as mock_create:
        # Setup mocks
        settings = MagicMock()
        settings.EXECUTION_ENABLED = False
        mock_settings.return_value = settings

        exec_service = MagicMock()
        mock_exec_service.return_value = exec_service

        client = MagicMock()
        mock_client.return_value = client

        mock_create.return_value = (PlanIngestionOutcome.CREATED, valid_plan_in.id)

        # Call create_plan
        outcome, plan_id = create_plan(valid_plan_in)

        # Verify outcome
        assert outcome == PlanIngestionOutcome.CREATED
        assert plan_id == valid_plan_in.id

        # Verify execution trigger was NOT called
        exec_service.trigger_spec_execution.assert_not_called()


def test_create_plan_idempotent_skips_execution_trigger(valid_plan_in):
    """Test create_plan skips execution trigger for idempotent ingestions."""
    with patch("app.dependencies.get_cached_settings") as mock_settings, patch(
        "app.dependencies.get_execution_service"
    ) as mock_exec_service, patch("app.dependencies.get_firestore_client") as mock_client, patch(
        "app.dependencies.firestore_service.create_plan_with_specs"
    ) as mock_create:
        # Setup mocks
        settings = MagicMock()
        settings.EXECUTION_ENABLED = True
        mock_settings.return_value = settings

        exec_service = MagicMock()
        mock_exec_service.return_value = exec_service

        client = MagicMock()
        mock_client.return_value = client

        mock_create.return_value = (PlanIngestionOutcome.IDENTICAL, valid_plan_in.id)

        # Call create_plan
        outcome, plan_id = create_plan(valid_plan_in)

        # Verify outcome
        assert outcome == PlanIngestionOutcome.IDENTICAL
        assert plan_id == valid_plan_in.id

        # Verify execution trigger was NOT called for idempotent ingestion
        exec_service.trigger_spec_execution.assert_not_called()


def test_create_plan_cleanup_on_execution_trigger_failure(valid_plan_in, mock_spec_record, caplog):
    """Test create_plan performs cleanup when execution trigger fails."""
    with patch("app.dependencies.get_cached_settings") as mock_settings, patch(
        "app.dependencies.get_execution_service"
    ) as mock_exec_service, patch("app.dependencies.get_firestore_client") as mock_client, patch(
        "app.dependencies.firestore_service.create_plan_with_specs"
    ) as mock_create, patch(
        "app.dependencies.firestore_service.delete_plan_with_specs"
    ) as mock_delete:
        # Setup mocks
        settings = MagicMock()
        settings.EXECUTION_ENABLED = True
        mock_settings.return_value = settings

        exec_service = MagicMock()
        exec_service.trigger_spec_execution.side_effect = Exception("Trigger failed")
        mock_exec_service.return_value = exec_service

        client = MagicMock()
        spec_doc_snapshot = MagicMock()
        spec_doc_snapshot.exists = True
        spec_doc_snapshot.to_dict.return_value = mock_spec_record.model_dump()
        client.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
            spec_doc_snapshot
        )
        mock_client.return_value = client

        mock_create.return_value = (PlanIngestionOutcome.CREATED, valid_plan_in.id)

        # Call create_plan and expect it to raise
        with caplog.at_level(logging.INFO):  # Capture both INFO and ERROR
            with pytest.raises(Exception) as exc_info:
                create_plan(valid_plan_in)

        # Verify the original error is raised
        assert "Trigger failed" in str(exc_info.value)

        # Verify cleanup was called
        mock_delete.assert_called_once_with(valid_plan_in.id, client=client)

        # Verify error logging
        error_messages = [
            record.message for record in caplog.records if record.levelname == "ERROR"
        ]
        assert any("Execution trigger failed" in msg for msg in error_messages)
        
        # Verify cleanup completion logging (at INFO level)
        info_messages = [
            record.message for record in caplog.records if record.levelname == "INFO"
        ]
        assert any("Cleanup completed" in msg for msg in info_messages)


def test_create_plan_logs_cleanup_failure_but_raises_original_error(
    valid_plan_in, mock_spec_record, caplog
):
    """Test create_plan logs cleanup failure but raises original error."""
    with patch("app.dependencies.get_cached_settings") as mock_settings, patch(
        "app.dependencies.get_execution_service"
    ) as mock_exec_service, patch("app.dependencies.get_firestore_client") as mock_client, patch(
        "app.dependencies.firestore_service.create_plan_with_specs"
    ) as mock_create, patch(
        "app.dependencies.firestore_service.delete_plan_with_specs"
    ) as mock_delete:
        # Setup mocks
        settings = MagicMock()
        settings.EXECUTION_ENABLED = True
        mock_settings.return_value = settings

        exec_service = MagicMock()
        exec_service.trigger_spec_execution.side_effect = Exception("Trigger failed")
        mock_exec_service.return_value = exec_service

        client = MagicMock()
        spec_doc_snapshot = MagicMock()
        spec_doc_snapshot.exists = True
        spec_doc_snapshot.to_dict.return_value = mock_spec_record.model_dump()
        client.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
            spec_doc_snapshot
        )
        mock_client.return_value = client

        mock_create.return_value = (PlanIngestionOutcome.CREATED, valid_plan_in.id)
        mock_delete.side_effect = Exception("Cleanup failed")

        # Call create_plan and expect it to raise original error
        with caplog.at_level(logging.ERROR):
            with pytest.raises(Exception) as exc_info:
                create_plan(valid_plan_in)

        # Verify the ORIGINAL error is raised, not cleanup error
        assert "Trigger failed" in str(exc_info.value)
        assert "Cleanup failed" not in str(exc_info.value)

        # Verify cleanup failure was logged
        error_messages = [
            record.message for record in caplog.records if record.levelname == "ERROR"
        ]
        assert any("Cleanup failed" in msg for msg in error_messages)


def test_create_plan_handles_spec_not_found_after_creation(valid_plan_in):
    """Test create_plan handles case where spec 0 is not found after creation."""
    with patch("app.dependencies.get_cached_settings") as mock_settings, patch(
        "app.dependencies.get_execution_service"
    ) as mock_exec_service, patch("app.dependencies.get_firestore_client") as mock_client, patch(
        "app.dependencies.firestore_service.create_plan_with_specs"
    ) as mock_create, patch(
        "app.dependencies.firestore_service.delete_plan_with_specs"
    ) as mock_delete:
        # Setup mocks
        settings = MagicMock()
        settings.EXECUTION_ENABLED = True
        mock_settings.return_value = settings

        exec_service = MagicMock()
        mock_exec_service.return_value = exec_service

        client = MagicMock()
        spec_doc_snapshot = MagicMock()
        spec_doc_snapshot.exists = False  # Spec not found
        client.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
            spec_doc_snapshot
        )
        mock_client.return_value = client

        mock_create.return_value = (PlanIngestionOutcome.CREATED, valid_plan_in.id)

        # Call create_plan and expect it to raise
        with pytest.raises(FirestoreOperationError) as exc_info:
            create_plan(valid_plan_in)

        assert "Spec 0 not found" in str(exc_info.value)

        # Verify cleanup was called
        mock_delete.assert_called_once()


def test_create_plan_propagates_conflict_error(valid_plan_in):
    """Test create_plan propagates PlanConflictError without cleanup."""
    with patch("app.dependencies.get_cached_settings") as mock_settings, patch(
        "app.dependencies.get_execution_service"
    ) as mock_exec_service, patch("app.dependencies.get_firestore_client") as mock_client, patch(
        "app.dependencies.firestore_service.create_plan_with_specs"
    ) as mock_create, patch(
        "app.dependencies.firestore_service.delete_plan_with_specs"
    ) as mock_delete:
        # Setup mocks
        settings = MagicMock()
        settings.EXECUTION_ENABLED = True
        mock_settings.return_value = settings

        exec_service = MagicMock()
        mock_exec_service.return_value = exec_service

        client = MagicMock()
        mock_client.return_value = client

        mock_create.side_effect = PlanConflictError(
            "Plan exists with different body", stored_digest="abc", incoming_digest="def"
        )

        # Call create_plan and expect conflict error
        with pytest.raises(PlanConflictError):
            create_plan(valid_plan_in)

        # Verify cleanup was NOT called (conflict happens before creation)
        mock_delete.assert_not_called()


def test_create_plan_propagates_firestore_operation_error(valid_plan_in):
    """Test create_plan propagates FirestoreOperationError without cleanup."""
    with patch("app.dependencies.get_cached_settings") as mock_settings, patch(
        "app.dependencies.get_execution_service"
    ) as mock_exec_service, patch("app.dependencies.get_firestore_client") as mock_client, patch(
        "app.dependencies.firestore_service.create_plan_with_specs"
    ) as mock_create, patch(
        "app.dependencies.firestore_service.delete_plan_with_specs"
    ) as mock_delete:
        # Setup mocks
        settings = MagicMock()
        settings.EXECUTION_ENABLED = True
        mock_settings.return_value = settings

        exec_service = MagicMock()
        mock_exec_service.return_value = exec_service

        client = MagicMock()
        mock_client.return_value = client

        mock_create.side_effect = FirestoreOperationError("Firestore failed")

        # Call create_plan and expect operation error
        with pytest.raises(FirestoreOperationError):
            create_plan(valid_plan_in)

        # Verify cleanup was NOT called (creation failed)
        mock_delete.assert_not_called()


def test_create_plan_logs_execution_trigger_attempt(valid_plan_in, mock_spec_record, caplog):
    """Test create_plan logs execution trigger attempt."""
    with patch("app.dependencies.get_cached_settings") as mock_settings, patch(
        "app.dependencies.get_execution_service"
    ) as mock_exec_service, patch("app.dependencies.get_firestore_client") as mock_client, patch(
        "app.dependencies.firestore_service.create_plan_with_specs"
    ) as mock_create:
        # Setup mocks
        settings = MagicMock()
        settings.EXECUTION_ENABLED = True
        mock_settings.return_value = settings

        exec_service = MagicMock()
        mock_exec_service.return_value = exec_service

        client = MagicMock()
        spec_doc_snapshot = MagicMock()
        spec_doc_snapshot.exists = True
        spec_doc_snapshot.to_dict.return_value = mock_spec_record.model_dump()
        client.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
            spec_doc_snapshot
        )
        mock_client.return_value = client

        mock_create.return_value = (PlanIngestionOutcome.CREATED, valid_plan_in.id)

        # Call create_plan
        with caplog.at_level(logging.INFO):
            create_plan(valid_plan_in)

        # Verify trigger attempt was logged
        info_messages = [record.message for record in caplog.records if record.levelname == "INFO"]
        assert any("Triggering execution for spec 0" in msg for msg in info_messages)


def test_create_plan_logs_execution_disabled_skip(valid_plan_in, caplog):
    """Test create_plan logs skip message when execution is disabled."""
    with patch("app.dependencies.get_cached_settings") as mock_settings, patch(
        "app.dependencies.get_execution_service"
    ) as mock_exec_service, patch("app.dependencies.get_firestore_client") as mock_client, patch(
        "app.dependencies.firestore_service.create_plan_with_specs"
    ) as mock_create:
        # Setup mocks
        settings = MagicMock()
        settings.EXECUTION_ENABLED = False
        mock_settings.return_value = settings

        exec_service = MagicMock()
        mock_exec_service.return_value = exec_service

        client = MagicMock()
        mock_client.return_value = client

        mock_create.return_value = (PlanIngestionOutcome.CREATED, valid_plan_in.id)

        # Call create_plan
        with caplog.at_level(logging.INFO):
            create_plan(valid_plan_in)

        # Verify skip was logged
        info_messages = [record.message for record in caplog.records if record.levelname == "INFO"]
        assert any("Execution disabled" in msg for msg in info_messages)
