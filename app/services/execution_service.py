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
"""Execution service abstraction for triggering spec execution.

This module provides:
1. ExecutionService class for triggering spec execution with structured logging
2. Configuration-based enable/disable toggle via EXECUTION_ENABLED flag
3. Extension points for future HTTP integration

Key Features:
- Structured logging with plan_id, spec_index, status, and serialized spec_data
- Configuration toggle to disable triggers while maintaining API surface
- Proper serialization of datetime/UUID fields to avoid logging errors
- Placeholders for future HTTP integration with URL/auth/retry handling

Future HTTP Integration:
- Add HTTP client (e.g., httpx) for making API calls
- Implement URL configuration for execution endpoint
- Add authentication headers (e.g., Bearer token, API key)
- Implement retry logic with exponential backoff
- Add timeout configuration for HTTP requests
- Handle HTTP errors and status codes appropriately
"""

import logging
from typing import Any

from app.config import get_settings
from app.models.plan import SpecRecord


class ExecutionService:
    """Service for triggering spec execution with structured logging.

    This service provides an abstraction layer for triggering external execution
    of specification tasks. It currently logs execution requests with full context
    and can be disabled via configuration for local development.

    Future enhancements will include:
    - HTTP API integration for triggering remote execution
    - Authentication and authorization
    - Retry logic with exponential backoff
    - Circuit breaker patterns for resilience
    """

    def __init__(self):
        """Initialize the execution service with configuration."""
        self.logger = logging.getLogger(__name__)
        self.settings = get_settings()

    def trigger_spec_execution(self, plan_id: str, spec_index: int, spec_data: SpecRecord) -> None:
        """Trigger execution of a specification.

        This method logs the execution trigger request with all relevant context.
        When EXECUTION_ENABLED is False, it logs a skip notice and returns without
        triggering execution.

        Args:
            plan_id: The unique identifier of the plan (UUID string)
            spec_index: The index of the specification in the plan (0-based)
            spec_data: The specification record containing purpose, vision, requirements, etc.

        Returns:
            None

        Future HTTP Integration:
        - POST request to configured execution endpoint (e.g., /api/v1/execute)
        - Request body will include plan_id, spec_index, and serialized spec_data
        - Authorization header with Bearer token or API key
        - Timeout configuration (default: 30 seconds)
        - Retry on 5xx errors with exponential backoff (max 3 retries)
        - Error handling for network issues and API errors

        Example future implementation:
            ```python
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.settings.EXECUTION_API_URL}/execute",
                    json={
                        "plan_id": plan_id,
                        "spec_index": spec_index,
                        "spec_data": self._serialize_spec_data(spec_data),
                    },
                    headers={
                        "Authorization": f"Bearer {self.settings.EXECUTION_API_TOKEN}",
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
            ```
        """
        if not self.settings.EXECUTION_ENABLED:
            self.logger.info(
                "Execution service disabled, skipping spec execution trigger",
                extra={
                    "plan_id": plan_id,
                    "spec_index": spec_index,
                    "status": spec_data.status,
                    "execution_enabled": False,
                },
            )
            return

        # Serialize spec_data to dict for logging, handling datetime/UUID fields
        serialized_spec_data = self._serialize_spec_data(spec_data)

        self.logger.info(
            "Triggering spec execution",
            extra={
                "plan_id": plan_id,
                "spec_index": spec_index,
                "status": spec_data.status,
                "spec_data": serialized_spec_data,
                "execution_enabled": True,
            },
        )

        # Future HTTP integration will go here
        # See docstring above for example implementation with httpx
        # TODO: Implement HTTP POST to execution API endpoint
        # TODO: Add retry logic with exponential backoff
        # TODO: Add circuit breaker for resilience
        # TODO: Add metrics collection for monitoring

    def _serialize_spec_data(self, spec_data: SpecRecord) -> dict[str, Any]:
        """Serialize SpecRecord to dict, converting datetime/UUID fields to strings.

        This method ensures that all fields in the spec_data are serializable
        for logging. Datetime fields are converted to ISO 8601 strings and UUID
        fields are converted to string representations.

        Args:
            spec_data: The specification record to serialize

        Returns:
            Dictionary with all fields serialized to JSON-safe types
        """
        # Use pydantic's model_dump with mode='json' to get a dict representation
        # with JSON-compatible types (e.g., datetime -> str, UUID -> str).
        # This handles nested structures and custom types automatically.
        return spec_data.model_dump(mode="json")
