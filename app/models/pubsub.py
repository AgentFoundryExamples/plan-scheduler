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
"""Pub/Sub payload models and validation helpers.

This module defines:
1. SpecStatusPayload - Inner payload containing spec execution status updates
2. PubSubMessage - The message object within the push envelope
3. PubSubPushEnvelope - Outer envelope for Pub/Sub push subscriptions
4. decode_pubsub_message - Helper to decode and validate base64-encoded messages

All models enforce that plan_id and spec_index are present to ensure Pub/Sub
callbacks can always resolve the relevant spec for updates.
"""

import base64
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SpecStatusPayload(BaseModel):
    """
    Specification status update payload.

    This represents the decoded inner payload that contains the actual
    spec execution status information. It must always include plan_id
    and spec_index so downstream handlers can identify which spec to update.

    Fields:
        plan_id: UUID string identifying the plan (required)
        spec_index: Zero-based index of the spec within the plan (required)
        status: Current status of the spec execution (required)
                Valid values: "blocked", "running", "finished", "failed"
        stage: Optional execution stage/phase information
    """

    plan_id: str = Field(..., description="Plan ID as UUID string - required for spec resolution")
    spec_index: int = Field(
        ...,
        description="Zero-based index of spec in plan - required for spec resolution",
        ge=0,
    )
    status: str = Field(
        ...,
        description="Spec execution status: blocked, running, finished, or failed",
        pattern="^(blocked|running|finished|failed)$",
    )
    stage: str | None = Field(
        default=None, description="Optional execution stage/phase information"
    )


class PubSubMessage(BaseModel):
    """
    Pub/Sub message object within the push envelope.

    This represents the 'message' field in the push request from Pub/Sub.
    The 'data' field contains base64-encoded JSON payload.

    Fields:
        data: Base64-encoded message payload (required)
        attributes: Optional key-value metadata attached to the message
        messageId: Unique identifier for this message
        publishTime: RFC3339 timestamp when message was published
    """

    data: str = Field(..., description="Base64-encoded message payload")
    attributes: dict[str, str] = Field(
        default_factory=dict, description="Optional message attributes/metadata"
    )
    messageId: str = Field(default="", description="Unique message ID assigned by Pub/Sub")
    publishTime: str = Field(default="", description="RFC3339 timestamp of message publication")

    @field_validator("publishTime", mode="before")
    @classmethod
    def validate_publish_time(cls, v: Any) -> str:
        """Accept both string and datetime, convert to string."""
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v) if v is not None else ""


class PubSubPushEnvelope(BaseModel):
    """
    Outer envelope for Pub/Sub push subscription requests.

    This model matches the JSON structure that Google Cloud Pub/Sub sends
    when pushing messages to HTTP endpoints. The actual payload is nested
    within message.data as base64-encoded JSON.

    Fields:
        message: The Pub/Sub message object containing data and metadata
        subscription: Full resource name of the subscription (e.g.,
                      "projects/my-project/subscriptions/my-sub")
    """

    message: PubSubMessage = Field(..., description="Pub/Sub message object")
    subscription: str = Field(default="", description="Full subscription resource name")


def decode_pubsub_message(encoded_data: str) -> dict[str, Any]:
    """
    Decode and parse a base64-encoded Pub/Sub message payload.

    This helper decodes message.data from base64, parses it as JSON, and
    returns the resulting dictionary. It provides descriptive error messages
    for common failure cases.

    Args:
        encoded_data: Base64-encoded string from message.data field

    Returns:
        Parsed JSON payload as a dictionary

    Raises:
        ValueError: If base64 decoding fails, JSON parsing fails, or the
                    decoded data is not valid JSON

    Examples:
        >>> import base64, json
        >>> payload = {"plan_id": "abc-123", "spec_index": 0, "status": "running"}
        >>> encoded = base64.b64encode(json.dumps(payload).encode()).decode()
        >>> decoded = decode_pubsub_message(encoded)
        >>> decoded["plan_id"]
        'abc-123'
    """
    if not encoded_data:
        raise ValueError("Message data is empty or missing")

    try:
        decoded_bytes = base64.b64decode(encoded_data)
    except Exception as e:
        raise ValueError(
            f"Failed to decode base64 message data: {e}. "
            "Ensure the message.data field contains valid base64."
        ) from e

    try:
        decoded_str = decoded_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(
            f"Failed to decode message as UTF-8: {e}. " "Message data must be UTF-8 encoded JSON."
        ) from e

    try:
        payload = json.loads(decoded_str)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Failed to parse message as JSON: {e}. " f"Decoded content: {decoded_str[:100]}"
        ) from e

    if not isinstance(payload, dict):
        raise ValueError(f"Message payload must be a JSON object, got {type(payload).__name__}")

    return payload
