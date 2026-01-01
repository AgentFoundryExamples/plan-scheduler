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
"""Tests for Pub/Sub payload models and helpers."""

import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.pubsub import (
    PubSubMessage,
    PubSubPushEnvelope,
    SpecStatusPayload,
    decode_pubsub_message,
)


class TestSpecStatusPayload:
    """Tests for SpecStatusPayload model."""

    def test_valid_payload_with_all_fields(self):
        """Test creating payload with all required and optional fields."""
        plan_id = str(uuid4())
        payload = SpecStatusPayload(
            plan_id=plan_id, spec_index=0, status="running", stage="initialization"
        )

        assert payload.plan_id == plan_id
        assert payload.spec_index == 0
        assert payload.status == "running"
        assert payload.stage == "initialization"

    def test_valid_payload_without_optional_stage(self):
        """Test creating payload without optional stage field."""
        plan_id = str(uuid4())
        payload = SpecStatusPayload(plan_id=plan_id, spec_index=2, status="finished")

        assert payload.plan_id == plan_id
        assert payload.spec_index == 2
        assert payload.status == "finished"
        assert payload.stage is None

    def test_valid_status_values(self):
        """Test all standard status values are accepted."""
        plan_id = str(uuid4())
        valid_statuses = ["blocked", "running", "finished", "failed"]

        for status in valid_statuses:
            payload = SpecStatusPayload(plan_id=plan_id, spec_index=0, status=status)
            assert payload.status == status

    def test_unknown_status_accepted(self):
        """Test that unknown status values are accepted and stored verbatim."""
        plan_id = str(uuid4())
        unknown_statuses = ["invalid", "CUSTOM_STATUS", "processing", "IN_PROGRESS"]

        for status in unknown_statuses:
            payload = SpecStatusPayload(plan_id=plan_id, spec_index=0, status=status)
            assert payload.status == status

    def test_uppercase_status_accepted(self):
        """Test that uppercase status values are accepted."""
        plan_id = str(uuid4())

        payload = SpecStatusPayload(plan_id=plan_id, spec_index=0, status="FINISHED")
        assert payload.status == "FINISHED"

    def test_missing_plan_id_rejected(self):
        """Test missing plan_id is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SpecStatusPayload(spec_index=0, status="running")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("plan_id",) for e in errors)

    def test_missing_spec_index_rejected(self):
        """Test missing spec_index is rejected."""
        plan_id = str(uuid4())

        with pytest.raises(ValidationError) as exc_info:
            SpecStatusPayload(plan_id=plan_id, status="running")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("spec_index",) for e in errors)

    def test_missing_status_rejected(self):
        """Test missing status is rejected."""
        plan_id = str(uuid4())

        with pytest.raises(ValidationError) as exc_info:
            SpecStatusPayload(plan_id=plan_id, spec_index=0)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("status",) for e in errors)

    def test_negative_spec_index_rejected(self):
        """Test negative spec_index is rejected."""
        plan_id = str(uuid4())

        with pytest.raises(ValidationError) as exc_info:
            SpecStatusPayload(plan_id=plan_id, spec_index=-1, status="running")

        errors = exc_info.value.errors()
        assert any("spec_index" in str(e) for e in errors)

    def test_zero_spec_index_accepted(self):
        """Test zero spec_index is valid."""
        plan_id = str(uuid4())
        payload = SpecStatusPayload(plan_id=plan_id, spec_index=0, status="running")

        assert payload.spec_index == 0

    def test_large_spec_index_accepted(self):
        """Test large spec_index values are accepted."""
        plan_id = str(uuid4())
        payload = SpecStatusPayload(plan_id=plan_id, spec_index=999, status="running")

        assert payload.spec_index == 999

    def test_optional_details_field(self):
        """Test optional details field is accepted."""
        plan_id = str(uuid4())
        payload = SpecStatusPayload(
            plan_id=plan_id,
            spec_index=0,
            status="running",
            details="Additional information about the status",
        )

        assert payload.details == "Additional information about the status"

    def test_optional_correlation_id_field(self):
        """Test optional correlation_id field is accepted."""
        plan_id = str(uuid4())
        payload = SpecStatusPayload(
            plan_id=plan_id,
            spec_index=0,
            status="running",
            correlation_id="trace-123-456",
        )

        assert payload.correlation_id == "trace-123-456"

    def test_optional_timestamp_field(self):
        """Test optional timestamp field is accepted."""
        plan_id = str(uuid4())
        timestamp = "2025-01-01T12:00:00Z"
        payload = SpecStatusPayload(
            plan_id=plan_id, spec_index=0, status="running", timestamp=timestamp
        )

        assert payload.timestamp == timestamp

    def test_all_optional_fields_together(self):
        """Test all optional fields can be used together."""
        plan_id = str(uuid4())
        payload = SpecStatusPayload(
            plan_id=plan_id,
            spec_index=0,
            status="running",
            stage="implementation",
            details="Currently implementing feature X",
            correlation_id="trace-abc-123",
            timestamp="2025-01-01T12:00:00Z",
        )

        assert payload.stage == "implementation"
        assert payload.details == "Currently implementing feature X"
        assert payload.correlation_id == "trace-abc-123"
        assert payload.timestamp == "2025-01-01T12:00:00Z"

    def test_optional_fields_default_to_none(self):
        """Test optional fields default to None when not provided."""
        plan_id = str(uuid4())
        payload = SpecStatusPayload(plan_id=plan_id, spec_index=0, status="running")

        assert payload.stage is None
        assert payload.details is None
        assert payload.correlation_id is None
        assert payload.timestamp is None

    def test_payload_serialization(self):
        """Test payload serializes correctly to dict."""
        plan_id = str(uuid4())
        payload = SpecStatusPayload(
            plan_id=plan_id, spec_index=1, status="running", stage="execution"
        )

        data = payload.model_dump()
        assert data["plan_id"] == plan_id
        assert data["spec_index"] == 1
        assert data["status"] == "running"
        assert data["stage"] == "execution"

    def test_payload_deserialization(self):
        """Test payload can be deserialized from dict."""
        plan_id = str(uuid4())
        data = {"plan_id": plan_id, "spec_index": 0, "status": "finished", "stage": None}

        payload = SpecStatusPayload.model_validate(data)
        assert payload.plan_id == plan_id
        assert payload.spec_index == 0
        assert payload.status == "finished"
        assert payload.stage is None


class TestPubSubMessage:
    """Tests for PubSubMessage model."""

    def test_message_with_all_fields(self):
        """Test creating message with all fields."""
        msg = PubSubMessage(
            data="aGVsbG8gd29ybGQ=",
            attributes={"key1": "value1", "key2": "value2"},
            messageId="123456789",
            publishTime="2025-01-15T10:30:00Z",
        )

        assert msg.data == "aGVsbG8gd29ybGQ="
        assert msg.attributes == {"key1": "value1", "key2": "value2"}
        assert msg.messageId == "123456789"
        assert msg.publishTime == "2025-01-15T10:30:00Z"

    def test_message_with_minimal_fields(self):
        """Test creating message with only required data field."""
        msg = PubSubMessage(data="dGVzdA==")

        assert msg.data == "dGVzdA=="
        assert msg.attributes == {}
        assert msg.messageId == ""
        assert msg.publishTime == ""

    def test_message_missing_data_rejected(self):
        """Test message without data field is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PubSubMessage()

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("data",) for e in errors)

    def test_message_with_empty_data(self):
        """Test message accepts empty string data."""
        msg = PubSubMessage(data="")
        assert msg.data == ""

    def test_message_with_empty_attributes(self):
        """Test message accepts empty attributes dict."""
        msg = PubSubMessage(data="dGVzdA==", attributes={})
        assert msg.attributes == {}

    def test_message_attributes_default_to_empty_dict(self):
        """Test attributes default to empty dict when not provided."""
        msg = PubSubMessage(data="dGVzdA==")
        assert msg.attributes == {}
        assert isinstance(msg.attributes, dict)

    def test_message_publish_time_accepts_datetime(self):
        """Test publishTime can be set with datetime object."""
        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        msg = PubSubMessage(data="dGVzdA==", publishTime=dt)

        # Should be converted to ISO format string
        assert isinstance(msg.publishTime, str)
        assert "2025-01-15" in msg.publishTime

    def test_message_serialization(self):
        """Test message serializes correctly to dict."""
        msg = PubSubMessage(
            data="dGVzdA==",
            attributes={"attr1": "val1"},
            messageId="msg-123",
            publishTime="2025-01-15T10:30:00Z",
        )

        data = msg.model_dump()
        assert data["data"] == "dGVzdA=="
        assert data["attributes"] == {"attr1": "val1"}
        assert data["messageId"] == "msg-123"
        assert data["publishTime"] == "2025-01-15T10:30:00Z"


class TestPubSubPushEnvelope:
    """Tests for PubSubPushEnvelope model."""

    def test_envelope_with_all_fields(self):
        """Test creating envelope with all fields."""
        msg = PubSubMessage(data="dGVzdA==", messageId="123", publishTime="2025-01-15T10:30:00Z")
        envelope = PubSubPushEnvelope(
            message=msg, subscription="projects/my-project/subscriptions/my-sub"
        )

        assert envelope.message.data == "dGVzdA=="
        assert envelope.subscription == "projects/my-project/subscriptions/my-sub"

    def test_envelope_with_minimal_fields(self):
        """Test creating envelope with only required message field."""
        msg = PubSubMessage(data="dGVzdA==")
        envelope = PubSubPushEnvelope(message=msg)

        assert envelope.message.data == "dGVzdA=="
        assert envelope.subscription == ""

    def test_envelope_missing_message_rejected(self):
        """Test envelope without message field is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PubSubPushEnvelope(subscription="projects/test/subscriptions/sub")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("message",) for e in errors)

    def test_envelope_subscription_defaults_to_empty(self):
        """Test subscription defaults to empty string."""
        msg = PubSubMessage(data="dGVzdA==")
        envelope = PubSubPushEnvelope(message=msg)

        assert envelope.subscription == ""

    def test_envelope_serialization(self):
        """Test envelope serializes correctly to dict."""
        msg = PubSubMessage(data="dGVzdA==", messageId="123")
        envelope = PubSubPushEnvelope(
            message=msg, subscription="projects/my-project/subscriptions/my-sub"
        )

        data = envelope.model_dump()
        assert "message" in data
        assert data["message"]["data"] == "dGVzdA=="
        assert data["subscription"] == "projects/my-project/subscriptions/my-sub"

    def test_envelope_deserialization(self):
        """Test envelope can be deserialized from dict."""
        data = {
            "message": {"data": "dGVzdA==", "messageId": "123", "publishTime": ""},
            "subscription": "projects/test/subscriptions/sub",
        }

        envelope = PubSubPushEnvelope.model_validate(data)
        assert envelope.message.data == "dGVzdA=="
        assert envelope.subscription == "projects/test/subscriptions/sub"

    def test_envelope_with_nested_attributes(self):
        """Test envelope with message attributes."""
        msg = PubSubMessage(data="dGVzdA==", attributes={"type": "status", "version": "1"})
        envelope = PubSubPushEnvelope(message=msg)

        assert envelope.message.attributes["type"] == "status"
        assert envelope.message.attributes["version"] == "1"


class TestDecodePubSubMessage:
    """Tests for decode_pubsub_message helper function."""

    def test_decode_valid_message(self):
        """Test decoding a valid base64-encoded JSON message."""
        payload = {"plan_id": str(uuid4()), "spec_index": 0, "status": "running"}
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()

        decoded = decode_pubsub_message(encoded)

        assert decoded["plan_id"] == payload["plan_id"]
        assert decoded["spec_index"] == 0
        assert decoded["status"] == "running"

    def test_decode_empty_data_raises_error(self):
        """Test decoding empty data raises descriptive error."""
        with pytest.raises(ValueError, match="Message data is empty or missing"):
            decode_pubsub_message("")

    def test_decode_invalid_base64_raises_error(self):
        """Test decoding invalid base64 raises descriptive error."""
        with pytest.raises(ValueError, match="Failed to decode base64 message data"):
            decode_pubsub_message("not-valid-base64!@#$")

    def test_decode_non_utf8_raises_error(self):
        """Test decoding non-UTF-8 data raises descriptive error."""
        # Encode invalid UTF-8 bytes
        invalid_bytes = b"\xff\xfe"
        encoded = base64.b64encode(invalid_bytes).decode()

        with pytest.raises(ValueError, match="Failed to decode message as UTF-8"):
            decode_pubsub_message(encoded)

    def test_decode_invalid_json_raises_error(self):
        """Test decoding invalid JSON raises descriptive error."""
        invalid_json = "not valid json"
        encoded = base64.b64encode(invalid_json.encode()).decode()

        with pytest.raises(ValueError, match="Failed to parse message as JSON"):
            decode_pubsub_message(encoded)

    def test_decode_non_object_json_raises_error(self):
        """Test decoding JSON array raises descriptive error."""
        json_array = json.dumps(["item1", "item2"])
        encoded = base64.b64encode(json_array.encode()).decode()

        with pytest.raises(ValueError, match="Message payload must be a JSON object"):
            decode_pubsub_message(encoded)

    def test_decode_json_string_raises_error(self):
        """Test decoding JSON string raises descriptive error."""
        json_string = json.dumps("just a string")
        encoded = base64.b64encode(json_string.encode()).decode()

        with pytest.raises(ValueError, match="Message payload must be a JSON object"):
            decode_pubsub_message(encoded)

    def test_decode_json_number_raises_error(self):
        """Test decoding JSON number raises descriptive error."""
        json_number = json.dumps(42)
        encoded = base64.b64encode(json_number.encode()).decode()

        with pytest.raises(ValueError, match="Message payload must be a JSON object"):
            decode_pubsub_message(encoded)

    def test_decode_message_with_special_characters(self):
        """Test decoding message with special characters."""
        payload = {"plan_id": "test-123", "status": "running", "note": "Special: émojis 🎉"}
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()

        decoded = decode_pubsub_message(encoded)

        assert decoded["note"] == "Special: émojis 🎉"

    def test_decode_message_with_nested_objects(self):
        """Test decoding message with nested objects."""
        payload = {
            "plan_id": "test-123",
            "spec_index": 0,
            "status": "running",
            "metadata": {"retries": 3, "tags": ["important", "production"]},
        }
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()

        decoded = decode_pubsub_message(encoded)

        assert decoded["metadata"]["retries"] == 3
        assert decoded["metadata"]["tags"] == ["important", "production"]

    def test_decode_message_with_null_values(self):
        """Test decoding message with null values."""
        payload = {"plan_id": "test-123", "spec_index": 0, "status": "running", "stage": None}
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()

        decoded = decode_pubsub_message(encoded)

        assert decoded["stage"] is None

    def test_decode_empty_object(self):
        """Test decoding empty JSON object is valid."""
        payload = {}
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()

        decoded = decode_pubsub_message(encoded)

        assert decoded == {}


class TestEndToEndPubSubFlow:
    """Integration tests for complete Pub/Sub message flow."""

    def test_full_message_decode_and_validation(self):
        """Test complete flow: encode -> envelope -> decode -> validate."""
        plan_id = str(uuid4())

        # 1. Create the inner payload
        payload = {"plan_id": plan_id, "spec_index": 2, "status": "finished", "stage": "cleanup"}

        # 2. Encode as base64
        encoded_data = base64.b64encode(json.dumps(payload).encode()).decode()

        # 3. Create Pub/Sub envelope
        envelope = PubSubPushEnvelope(
            message=PubSubMessage(
                data=encoded_data,
                messageId="msg-12345",
                publishTime="2025-01-15T10:30:00Z",
                attributes={"source": "execution-service"},
            ),
            subscription="projects/my-project/subscriptions/spec-status",
        )

        # 4. Decode the message data
        decoded = decode_pubsub_message(envelope.message.data)

        # 5. Validate as SpecStatusPayload
        status_payload = SpecStatusPayload.model_validate(decoded)

        assert status_payload.plan_id == plan_id
        assert status_payload.spec_index == 2
        assert status_payload.status == "finished"
        assert status_payload.stage == "cleanup"

    def test_message_missing_required_field_fails_validation(self):
        """Test that decoded message missing required fields fails validation."""
        # Missing spec_index
        payload = {"plan_id": str(uuid4()), "status": "running"}
        encoded_data = base64.b64encode(json.dumps(payload).encode()).decode()

        decoded = decode_pubsub_message(encoded_data)

        with pytest.raises(ValidationError) as exc_info:
            SpecStatusPayload.model_validate(decoded)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("spec_index",) for e in errors)

    def test_message_with_custom_status_accepted(self):
        """Test that decoded message with custom status is accepted."""
        payload = {"plan_id": str(uuid4()), "spec_index": 0, "status": "custom-status"}
        encoded_data = base64.b64encode(json.dumps(payload).encode()).decode()

        decoded = decode_pubsub_message(encoded_data)

        # Should not raise ValidationError - custom statuses are now accepted
        status_payload = SpecStatusPayload.model_validate(decoded)
        assert status_payload.status == "custom-status"

    def test_real_pubsub_push_request_structure(self):
        """Test parsing a realistic Pub/Sub push request payload."""
        # Simulate a real Pub/Sub push request
        push_request = {
            "message": {
                "data": base64.b64encode(
                    json.dumps(
                        {
                            "plan_id": str(uuid4()),
                            "spec_index": 1,
                            "status": "running",
                            "stage": "initialization",
                        }
                    ).encode()
                ).decode(),
                "messageId": "1234567890",
                "publishTime": "2025-01-15T10:30:00.123Z",
                "attributes": {"source": "execution-service", "version": "1.0"},
            },
            "subscription": "projects/my-project/subscriptions/spec-status-updates",
        }

        # Parse the envelope
        envelope = PubSubPushEnvelope.model_validate(push_request)

        # Decode and validate the payload
        decoded = decode_pubsub_message(envelope.message.data)
        payload = SpecStatusPayload.model_validate(decoded)

        assert payload.status == "running"
        assert payload.stage == "initialization"
        assert envelope.message.attributes["source"] == "execution-service"
