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
"""Tests for unified Pub/Sub event handling with enhanced idempotency and observability."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.firestore_service import process_spec_status_update


class TestEnhancedIdempotency:
    """Test enhanced idempotency with correlation_id and message_id."""

    @pytest.fixture
    def mock_firestore_client(self):
        """Create a mock Firestore client."""
        return MagicMock()

    @pytest.fixture
    def mock_transactional(self):
        """Mock the transactional decorator to execute immediately."""

        def decorator(func):
            def wrapper(transaction):
                return func(transaction)

            return wrapper

        return decorator

    def test_correlation_id_idempotency_prevents_duplicate_terminal_event(
        self, mock_firestore_client, mock_transactional
    ):
        """Test that duplicate correlation_id prevents reprocessing terminal events."""
        plan_id = str(uuid.uuid4())
        correlation_id = "test-correlation-123"

        # Mock plan and spec with existing history entry containing correlation_id
        mock_plan_snapshot = MagicMock()
        mock_plan_snapshot.exists = True
        mock_plan_snapshot.to_dict.return_value = {
            "plan_id": plan_id,
            "overall_status": "running",
            "completed_specs": 0,
            "total_specs": 2,
            "current_spec_index": 0,
        }

        mock_spec_snapshot = MagicMock()
        mock_spec_snapshot.exists = True
        mock_spec_snapshot.to_dict.return_value = {
            "spec_index": 0,
            "status": "running",
            "history": [
                {
                    "timestamp": "2025-01-01T12:00:00Z",
                    "received_status": "finished",
                    "correlation_id": correlation_id,
                    "message_id": "old-message-id",
                }
            ],
        }

        mock_plan_ref = MagicMock()
        mock_plan_ref.get.return_value = mock_plan_snapshot

        mock_spec_ref = MagicMock()
        mock_spec_ref.get.return_value = mock_spec_snapshot

        mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref
        mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

        with patch("app.services.firestore_service.firestore.transactional", mock_transactional):
            result = process_spec_status_update(
                plan_id=plan_id,
                spec_index=0,
                status="finished",
                stage=None,
                message_id="new-message-id",  # Different message_id
                correlation_id=correlation_id,  # Same correlation_id
                raw_payload_snippet={},
                client=mock_firestore_client,
            )

        # Verify idempotency was triggered
        assert result["success"] is True
        assert result["action"] == "duplicate"
        assert correlation_id in result["message"]

    def test_message_id_idempotency_as_fallback(self, mock_firestore_client, mock_transactional):
        """Test that message_id works as fallback when no correlation_id provided."""
        plan_id = str(uuid.uuid4())
        message_id = "test-message-123"

        # Mock plan and spec with existing history entry containing message_id
        mock_plan_snapshot = MagicMock()
        mock_plan_snapshot.exists = True
        mock_plan_snapshot.to_dict.return_value = {
            "plan_id": plan_id,
            "overall_status": "running",
            "completed_specs": 0,
            "total_specs": 2,
            "current_spec_index": 0,
        }

        mock_spec_snapshot = MagicMock()
        mock_spec_snapshot.exists = True
        mock_spec_snapshot.to_dict.return_value = {
            "spec_index": 0,
            "status": "running",
            "history": [
                {
                    "timestamp": "2025-01-01T12:00:00Z",
                    "received_status": "finished",
                    "correlation_id": None,
                    "message_id": message_id,
                }
            ],
        }

        mock_plan_ref = MagicMock()
        mock_plan_ref.get.return_value = mock_plan_snapshot

        mock_spec_ref = MagicMock()
        mock_spec_ref.get.return_value = mock_spec_snapshot

        mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref
        mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

        with patch("app.services.firestore_service.firestore.transactional", mock_transactional):
            result = process_spec_status_update(
                plan_id=plan_id,
                spec_index=0,
                status="finished",
                stage=None,
                message_id=message_id,  # Same message_id
                correlation_id=None,  # No correlation_id
                raw_payload_snippet={},
                client=mock_firestore_client,
            )

        # Verify idempotency was triggered via message_id
        assert result["success"] is True
        assert result["action"] == "duplicate"
        assert message_id in result["message"]

    def test_correlation_id_takes_precedence_over_message_id(
        self, mock_firestore_client, mock_transactional
    ):
        """Test that correlation_id check takes precedence over message_id."""
        plan_id = str(uuid.uuid4())
        correlation_id = "test-correlation-123"

        # Mock plan and spec with history containing matching correlation_id
        mock_plan_snapshot = MagicMock()
        mock_plan_snapshot.exists = True
        mock_plan_snapshot.to_dict.return_value = {
            "plan_id": plan_id,
            "overall_status": "running",
            "completed_specs": 0,
            "total_specs": 2,
            "current_spec_index": 0,
        }

        mock_spec_snapshot = MagicMock()
        mock_spec_snapshot.exists = True
        mock_spec_snapshot.to_dict.return_value = {
            "spec_index": 0,
            "status": "running",
            "history": [
                {
                    "timestamp": "2025-01-01T12:00:00Z",
                    "received_status": "finished",
                    "correlation_id": correlation_id,
                    "message_id": "old-message-id",
                }
            ],
        }

        mock_plan_ref = MagicMock()
        mock_plan_ref.get.return_value = mock_plan_snapshot

        mock_spec_ref = MagicMock()
        mock_spec_ref.get.return_value = mock_spec_snapshot

        mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref
        mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

        with patch("app.services.firestore_service.firestore.transactional", mock_transactional):
            result = process_spec_status_update(
                plan_id=plan_id,
                spec_index=0,
                status="finished",
                stage=None,
                message_id="new-different-message-id",  # Different message_id
                correlation_id=correlation_id,  # Same correlation_id
                raw_payload_snippet={},
                client=mock_firestore_client,
            )

        # Verify correlation_id idempotency was triggered (not message_id)
        assert result["success"] is True
        assert result["action"] == "duplicate"
        assert "correlation_id" in result["message"]


class TestDetailedStatusField:
    """Test the detailed_status field for non-terminal status updates."""

    @pytest.fixture
    def mock_firestore_client(self):
        """Create a mock Firestore client."""
        return MagicMock()

    @pytest.fixture
    def mock_transactional(self):
        """Mock the transactional decorator to execute immediately."""

        def decorator(func):
            def wrapper(transaction):
                return func(transaction)

            return wrapper

        return decorator

    def test_non_terminal_status_updates_detailed_status_field(
        self, mock_firestore_client, mock_transactional
    ):
        """Test that non-terminal status updates set the detailed_status field."""
        plan_id = str(uuid.uuid4())

        # Mock plan and spec in running state
        mock_plan_snapshot = MagicMock()
        mock_plan_snapshot.exists = True
        mock_plan_snapshot.to_dict.return_value = {
            "plan_id": plan_id,
            "overall_status": "running",
            "completed_specs": 0,
            "total_specs": 2,
            "current_spec_index": 0,
        }

        mock_spec_snapshot = MagicMock()
        mock_spec_snapshot.exists = True
        mock_spec_snapshot.to_dict.return_value = {
            "spec_index": 0,
            "status": "running",
            "history": [],
        }

        mock_plan_ref = MagicMock()
        mock_plan_ref.get.return_value = mock_plan_snapshot
        mock_plan_ref.update = MagicMock()

        mock_spec_ref = MagicMock()
        mock_spec_ref.get.return_value = mock_spec_snapshot
        mock_spec_ref.update = MagicMock()

        mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref
        mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

        # Track transaction updates
        transaction_updates = {}

        def mock_transaction_update(ref, updates):
            transaction_updates[ref] = updates

        mock_transaction = MagicMock()
        mock_transaction.update = mock_transaction_update

        def mock_decorator(func):
            def wrapper(transaction):
                return func(mock_transaction)

            return wrapper

        with patch("app.services.firestore_service.firestore.transactional", mock_decorator):
            result = process_spec_status_update(
                plan_id=plan_id,
                spec_index=0,
                status="implementing",  # Non-terminal status
                stage="code_generation",
                message_id="test-msg-123",
                correlation_id="test-correlation-123",
                raw_payload_snippet={},
                client=mock_firestore_client,
            )

        # Verify result
        assert result["success"] is True
        assert result["action"] == "updated"
        assert "non-terminal" in result["message"].lower()

        # Verify spec updates include detailed_status
        spec_updates = transaction_updates.get(mock_spec_ref)
        assert spec_updates is not None
        assert spec_updates["detailed_status"] == "implementing"
        assert spec_updates["current_stage"] == "code_generation"
        # Main status should not be updated for non-terminal statuses
        assert "status" not in spec_updates or spec_updates.get("status") == "running"

    def test_non_terminal_status_without_stage(self, mock_firestore_client, mock_transactional):
        """Test non-terminal status update without stage field."""
        plan_id = str(uuid.uuid4())

        # Mock plan and spec in running state
        mock_plan_snapshot = MagicMock()
        mock_plan_snapshot.exists = True
        mock_plan_snapshot.to_dict.return_value = {
            "plan_id": plan_id,
            "overall_status": "running",
            "completed_specs": 0,
            "total_specs": 2,
            "current_spec_index": 0,
        }

        mock_spec_snapshot = MagicMock()
        mock_spec_snapshot.exists = True
        mock_spec_snapshot.to_dict.return_value = {
            "spec_index": 0,
            "status": "running",
            "history": [],
        }

        mock_plan_ref = MagicMock()
        mock_plan_ref.get.return_value = mock_plan_snapshot

        mock_spec_ref = MagicMock()
        mock_spec_ref.get.return_value = mock_spec_snapshot

        mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref
        mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

        # Track transaction updates
        transaction_updates = {}

        def mock_transaction_update(ref, updates):
            transaction_updates[ref] = updates

        mock_transaction = MagicMock()
        mock_transaction.update = mock_transaction_update

        def mock_decorator(func):
            def wrapper(transaction):
                return func(mock_transaction)

            return wrapper

        with patch("app.services.firestore_service.firestore.transactional", mock_decorator):
            result = process_spec_status_update(
                plan_id=plan_id,
                spec_index=0,
                status="processing",  # Non-terminal status
                stage=None,  # No stage provided
                message_id="test-msg-124",
                correlation_id=None,
                raw_payload_snippet={},
                client=mock_firestore_client,
            )

        # Verify result
        assert result["success"] is True
        assert result["action"] == "updated"

        # Verify spec updates include detailed_status but not current_stage
        spec_updates = transaction_updates.get(mock_spec_ref)
        assert spec_updates is not None
        assert spec_updates["detailed_status"] == "processing"
        assert "current_stage" not in spec_updates  # Should not be set when stage is None


class TestStructuredLogging:
    """Test structured logging for terminal vs non-terminal events."""

    @pytest.fixture
    def mock_firestore_client(self):
        """Create a mock Firestore client."""
        return MagicMock()

    @pytest.fixture
    def mock_transactional(self):
        """Mock the transactional decorator."""

        def decorator(func):
            def wrapper(transaction):
                return func(transaction)

            return wrapper

        return decorator

    def test_terminal_status_logs_include_event_type(
        self, mock_firestore_client, mock_transactional, caplog
    ):
        """Test that terminal status updates include event_type in logs."""
        plan_id = str(uuid.uuid4())

        # Mock plan and spec
        mock_plan_snapshot = MagicMock()
        mock_plan_snapshot.exists = True
        mock_plan_snapshot.to_dict.return_value = {
            "plan_id": plan_id,
            "overall_status": "running",
            "completed_specs": 0,
            "total_specs": 1,
            "current_spec_index": 0,
        }

        mock_spec_snapshot = MagicMock()
        mock_spec_snapshot.exists = True
        mock_spec_snapshot.to_dict.return_value = {
            "spec_index": 0,
            "status": "running",
            "history": [],
        }

        mock_plan_ref = MagicMock()
        mock_plan_ref.get.return_value = mock_plan_snapshot
        mock_plan_ref.update = MagicMock()

        mock_spec_ref = MagicMock()
        mock_spec_ref.get.return_value = mock_spec_snapshot
        mock_spec_ref.update = MagicMock()

        mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref
        mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

        mock_transaction = MagicMock()

        def mock_decorator(func):
            def wrapper(transaction):
                return func(mock_transaction)

            return wrapper

        with caplog.at_level("INFO"):
            with patch("app.services.firestore_service.firestore.transactional", mock_decorator):
                result = process_spec_status_update(
                    plan_id=plan_id,
                    spec_index=0,
                    status="finished",  # Terminal status
                    stage=None,
                    message_id="test-msg-125",
                    correlation_id=None,
                    raw_payload_snippet={},
                    client=mock_firestore_client,
                )

        # Verify result
        assert result["success"] is True
        assert result["plan_finished"] is True

        # Verify structured logging includes event_type
        log_records = [record for record in caplog.records if "event_type" in record.__dict__]
        assert len(log_records) > 0
        terminal_logs = [
            record for record in log_records if "terminal" in record.__dict__.get("event_type", "")
        ]
        assert len(terminal_logs) > 0

    def test_non_terminal_status_logs_include_event_type(
        self, mock_firestore_client, mock_transactional, caplog
    ):
        """Test that non-terminal status updates include event_type in logs."""
        plan_id = str(uuid.uuid4())

        # Mock plan and spec
        mock_plan_snapshot = MagicMock()
        mock_plan_snapshot.exists = True
        mock_plan_snapshot.to_dict.return_value = {
            "plan_id": plan_id,
            "overall_status": "running",
            "completed_specs": 0,
            "total_specs": 2,
            "current_spec_index": 0,
        }

        mock_spec_snapshot = MagicMock()
        mock_spec_snapshot.exists = True
        mock_spec_snapshot.to_dict.return_value = {
            "spec_index": 0,
            "status": "running",
            "history": [],
        }

        mock_plan_ref = MagicMock()
        mock_plan_ref.get.return_value = mock_plan_snapshot
        mock_plan_ref.update = MagicMock()

        mock_spec_ref = MagicMock()
        mock_spec_ref.get.return_value = mock_spec_snapshot
        mock_spec_ref.update = MagicMock()

        mock_plan_ref.collection.return_value.document.return_value = mock_spec_ref
        mock_firestore_client.collection.return_value.document.return_value = mock_plan_ref

        mock_transaction = MagicMock()

        def mock_decorator(func):
            def wrapper(transaction):
                return func(mock_transaction)

            return wrapper

        with caplog.at_level("INFO"):
            with patch("app.services.firestore_service.firestore.transactional", mock_decorator):
                result = process_spec_status_update(
                    plan_id=plan_id,
                    spec_index=0,
                    status="analyzing",  # Non-terminal status
                    stage="analysis",
                    message_id="test-msg-126",
                    correlation_id=None,
                    raw_payload_snippet={},
                    client=mock_firestore_client,
                )

        # Verify result
        assert result["success"] is True

        # Verify structured logging includes event_type for non-terminal
        log_records = [record for record in caplog.records if "event_type" in record.__dict__]
        assert len(log_records) > 0
        non_terminal_logs = [
            record
            for record in log_records
            if record.__dict__.get("event_type") == "non_terminal_update"
        ]
        assert len(non_terminal_logs) > 0
        # Verify is_terminal flag is False
        assert non_terminal_logs[0].__dict__.get("is_terminal") is False
