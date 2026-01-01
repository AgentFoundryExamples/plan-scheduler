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
"""Tests for Pub/Sub API endpoints."""

import base64
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def valid_spec_status_payload():
    """Create a valid spec status payload."""
    return {
        "plan_id": str(uuid.uuid4()),
        "spec_index": 0,
        "status": "finished",
        "stage": "implementation",
    }


@pytest.fixture
def valid_pubsub_envelope(valid_spec_status_payload):
    """Create a valid Pub/Sub push envelope."""
    # Encode payload as base64
    payload_json = json.dumps(valid_spec_status_payload)
    encoded_data = base64.b64encode(payload_json.encode()).decode()

    return {
        "message": {
            "data": encoded_data,
            "messageId": "test-message-id-123",
            "publishTime": "2025-01-01T12:00:00Z",
            "attributes": {},
        },
        "subscription": "projects/test-project/subscriptions/test-sub",
    }


class TestSpecStatusEndpointAuthentication:
    """Test authentication and security for the spec-status endpoint."""

    def test_missing_verification_token_returns_401(self, client, valid_pubsub_envelope):
        """Test that missing verification token returns 401."""
        response = client.post("/pubsub/spec-status", json=valid_pubsub_envelope)
        assert response.status_code == 401
        assert "detail" in response.json()

    def test_invalid_verification_token_returns_401(self, client, valid_pubsub_envelope):
        """Test that invalid verification token returns 401."""
        response = client.post(
            "/pubsub/spec-status",
            json=valid_pubsub_envelope,
            headers={"x-goog-pubsub-verification-token": "invalid-token"},
        )
        assert response.status_code == 401
        assert "detail" in response.json()

    @patch("app.api.pubsub.get_settings")
    @patch("app.api.pubsub.process_spec_status_update")
    @patch("app.api.pubsub.get_client")
    def test_valid_verification_token_succeeds(
        self, mock_get_client, mock_process, mock_get_settings, client, valid_pubsub_envelope
    ):
        """Test that valid verification token allows request."""
        # Setup mocks
        mock_settings = MagicMock()
        mock_settings.PUBSUB_VERIFICATION_TOKEN = "test-token"
        mock_get_settings.return_value = mock_settings

        mock_process.return_value = {
            "success": True,
            "action": "updated",
            "next_spec_triggered": False,
            "plan_finished": False,
            "message": "Success",
        }

        response = client.post(
            "/pubsub/spec-status",
            json=valid_pubsub_envelope,
            headers={"x-goog-pubsub-verification-token": "test-token"},
        )
        assert response.status_code == 204


class TestSpecStatusEndpointPayloadValidation:
    """Test payload validation for the spec-status endpoint."""

    @patch("app.api.pubsub.get_settings")
    def test_invalid_base64_returns_400(self, mock_get_settings, client):
        """Test that invalid base64 data returns 400."""
        mock_settings = MagicMock()
        mock_settings.PUBSUB_VERIFICATION_TOKEN = "test-token"
        mock_get_settings.return_value = mock_settings

        envelope = {
            "message": {
                "data": "not-valid-base64!!!",
                "messageId": "test-msg",
                "publishTime": "2025-01-01T12:00:00Z",
            }
        }

        response = client.post(
            "/pubsub/spec-status",
            json=envelope,
            headers={"x-goog-pubsub-verification-token": "test-token"},
        )
        assert response.status_code == 400

    @patch("app.api.pubsub.get_settings")
    def test_invalid_json_returns_400(self, mock_get_settings, client):
        """Test that invalid JSON payload returns 400."""
        mock_settings = MagicMock()
        mock_settings.PUBSUB_VERIFICATION_TOKEN = "test-token"
        mock_get_settings.return_value = mock_settings

        # Encode non-JSON string as base64
        encoded_data = base64.b64encode(b"not json").decode()
        envelope = {
            "message": {
                "data": encoded_data,
                "messageId": "test-msg",
                "publishTime": "2025-01-01T12:00:00Z",
            }
        }

        response = client.post(
            "/pubsub/spec-status",
            json=envelope,
            headers={"x-goog-pubsub-verification-token": "test-token"},
        )
        assert response.status_code == 400

    @patch("app.api.pubsub.get_settings")
    def test_missing_required_field_returns_400(self, mock_get_settings, client):
        """Test that missing required fields return 400."""
        mock_settings = MagicMock()
        mock_settings.PUBSUB_VERIFICATION_TOKEN = "test-token"
        mock_get_settings.return_value = mock_settings

        # Missing spec_index
        payload = {"plan_id": str(uuid.uuid4()), "status": "finished"}
        encoded_data = base64.b64encode(json.dumps(payload).encode()).decode()
        envelope = {
            "message": {
                "data": encoded_data,
                "messageId": "test-msg",
                "publishTime": "2025-01-01T12:00:00Z",
            }
        }

        response = client.post(
            "/pubsub/spec-status",
            json=envelope,
            headers={"x-goog-pubsub-verification-token": "test-token"},
        )
        assert response.status_code == 400

    @patch("app.api.pubsub.get_settings")
    @patch("app.api.pubsub.get_client")
    @patch("app.api.pubsub.process_spec_status_update")
    def test_custom_status_value_accepted(
        self, mock_process_update, mock_get_client, mock_get_settings, client
    ):
        """Test that custom/unknown status values are accepted as informational statuses."""
        mock_settings = MagicMock()
        mock_settings.PUBSUB_VERIFICATION_TOKEN = "test-token"
        mock_get_settings.return_value = mock_settings

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_process_update.return_value = {
            "success": True,
            "action": "updated",
            "message": "Status updated",
        }

        payload = {
            "plan_id": str(uuid.uuid4()),
            "spec_index": 0,
            "status": "CUSTOM_STATUS",
        }
        encoded_data = base64.b64encode(json.dumps(payload).encode()).decode()
        envelope = {
            "message": {
                "data": encoded_data,
                "messageId": "test-msg",
                "publishTime": "2025-01-01T12:00:00Z",
            }
        }

        response = client.post(
            "/pubsub/spec-status",
            json=envelope,
            headers={"x-goog-pubsub-verification-token": "test-token"},
        )
        assert response.status_code == 204
        mock_process_update.assert_called_once()


class TestSpecStatusEndpointProcessing:
    """Test status update processing for the spec-status endpoint."""

    @patch("app.api.pubsub.get_settings")
    @patch("app.api.pubsub.process_spec_status_update")
    @patch("app.api.pubsub.get_client")
    def test_successful_update_returns_204(
        self,
        mock_get_client,
        mock_process,
        mock_get_settings,
        client,
        valid_pubsub_envelope,
    ):
        """Test that successful update returns 204."""
        mock_settings = MagicMock()
        mock_settings.PUBSUB_VERIFICATION_TOKEN = "test-token"
        mock_get_settings.return_value = mock_settings

        mock_process.return_value = {
            "success": True,
            "action": "updated",
            "next_spec_triggered": False,
            "plan_finished": False,
            "message": "Success",
        }

        response = client.post(
            "/pubsub/spec-status",
            json=valid_pubsub_envelope,
            headers={"x-goog-pubsub-verification-token": "test-token"},
        )
        assert response.status_code == 204
        assert mock_process.called

    @patch("app.api.pubsub.get_settings")
    @patch("app.api.pubsub.process_spec_status_update")
    @patch("app.api.pubsub.get_client")
    def test_duplicate_message_returns_204(
        self,
        mock_get_client,
        mock_process,
        mock_get_settings,
        client,
        valid_pubsub_envelope,
    ):
        """Test that duplicate message returns 204."""
        mock_settings = MagicMock()
        mock_settings.PUBSUB_VERIFICATION_TOKEN = "test-token"
        mock_get_settings.return_value = mock_settings

        mock_process.return_value = {
            "success": True,
            "action": "duplicate",
            "next_spec_triggered": False,
            "plan_finished": False,
            "message": "Duplicate",
        }

        response = client.post(
            "/pubsub/spec-status",
            json=valid_pubsub_envelope,
            headers={"x-goog-pubsub-verification-token": "test-token"},
        )
        assert response.status_code == 204

    @patch("app.api.pubsub.get_settings")
    @patch("app.api.pubsub.process_spec_status_update")
    @patch("app.api.pubsub.get_client")
    def test_not_found_returns_204(
        self,
        mock_get_client,
        mock_process,
        mock_get_settings,
        client,
        valid_pubsub_envelope,
    ):
        """Test that not found plan/spec returns 204 (graceful handling)."""
        mock_settings = MagicMock()
        mock_settings.PUBSUB_VERIFICATION_TOKEN = "test-token"
        mock_get_settings.return_value = mock_settings

        mock_process.return_value = {
            "success": False,
            "action": "not_found",
            "next_spec_triggered": False,
            "plan_finished": False,
            "message": "Not found",
        }

        response = client.post(
            "/pubsub/spec-status",
            json=valid_pubsub_envelope,
            headers={"x-goog-pubsub-verification-token": "test-token"},
        )
        assert response.status_code == 204

    @patch("app.api.pubsub.get_settings")
    @patch("app.api.pubsub.process_spec_status_update")
    @patch("app.api.pubsub.get_client")
    def test_firestore_error_returns_500(
        self,
        mock_get_client,
        mock_process,
        mock_get_settings,
        client,
        valid_pubsub_envelope,
    ):
        """Test that Firestore errors return 500."""
        mock_settings = MagicMock()
        mock_settings.PUBSUB_VERIFICATION_TOKEN = "test-token"
        mock_get_settings.return_value = mock_settings

        from app.services.firestore_service import FirestoreOperationError

        mock_process.side_effect = FirestoreOperationError("Firestore error")

        response = client.post(
            "/pubsub/spec-status",
            json=valid_pubsub_envelope,
            headers={"x-goog-pubsub-verification-token": "test-token"},
        )
        assert response.status_code == 500


class TestSpecStatusEndpointExecutionTrigger:
    """Test execution triggering for the spec-status endpoint."""

    @patch("app.api.pubsub.get_settings")
    @patch("app.api.pubsub.process_spec_status_update")
    @patch("app.api.pubsub.get_client")
    @patch("app.api.pubsub.ExecutionService")
    def test_next_spec_triggered_calls_execution_service(
        self,
        mock_exec_service_class,
        mock_get_client,
        mock_process,
        mock_get_settings,
        client,
        valid_pubsub_envelope,
    ):
        """Test that next spec triggering calls ExecutionService."""
        from datetime import UTC, datetime

        from app.models.plan import SpecRecord

        mock_settings = MagicMock()
        mock_settings.PUBSUB_VERIFICATION_TOKEN = "test-token"
        mock_get_settings.return_value = mock_settings

        mock_process.return_value = {
            "success": True,
            "action": "updated",
            "next_spec_triggered": True,
            "plan_finished": False,
            "message": "Success",
        }

        # Mock next spec fetch
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_spec_snapshot = MagicMock()
        mock_spec_snapshot.exists = True
        mock_spec_snapshot.to_dict.return_value = SpecRecord(
            spec_index=1,
            purpose="Test",
            vision="Test",
            status="running",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ).model_dump()

        mock_collection_chain = (
            mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value
        )
        mock_collection_chain.get.return_value = mock_spec_snapshot

        # Mock execution service
        mock_exec_service = MagicMock()
        mock_exec_service_class.return_value = mock_exec_service

        response = client.post(
            "/pubsub/spec-status",
            json=valid_pubsub_envelope,
            headers={"x-goog-pubsub-verification-token": "test-token"},
        )
        assert response.status_code == 204
        assert mock_exec_service.trigger_spec_execution.called

    @patch("app.api.pubsub.get_settings")
    @patch("app.api.pubsub.process_spec_status_update")
    @patch("app.api.pubsub.get_client")
    @patch("app.api.pubsub.ExecutionService")
    def test_execution_trigger_failure_logged_but_returns_204(
        self,
        mock_exec_service_class,
        mock_get_client,
        mock_process,
        mock_get_settings,
        client,
        valid_pubsub_envelope,
    ):
        """Test that execution trigger failures are logged but don't fail request."""
        from datetime import UTC, datetime

        from app.models.plan import SpecRecord

        mock_settings = MagicMock()
        mock_settings.PUBSUB_VERIFICATION_TOKEN = "test-token"
        mock_get_settings.return_value = mock_settings

        mock_process.return_value = {
            "success": True,
            "action": "updated",
            "next_spec_triggered": True,
            "plan_finished": False,
            "message": "Success",
        }

        # Mock next spec fetch
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_spec_snapshot = MagicMock()
        mock_spec_snapshot.exists = True
        mock_spec_snapshot.to_dict.return_value = SpecRecord(
            spec_index=1,
            purpose="Test",
            vision="Test",
            status="running",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ).model_dump()

        mock_collection_chain = (
            mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value
        )
        mock_collection_chain.get.return_value = mock_spec_snapshot

        # Mock execution service to raise exception
        mock_exec_service = MagicMock()
        mock_exec_service.trigger_spec_execution.side_effect = Exception("Trigger failed")
        mock_exec_service_class.return_value = mock_exec_service

        response = client.post(
            "/pubsub/spec-status",
            json=valid_pubsub_envelope,
            headers={"x-goog-pubsub-verification-token": "test-token"},
        )
        # Should still return 204 even if execution trigger fails
        assert response.status_code == 204
