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
"""Application configuration using pydantic BaseSettings."""

import logging
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    # Firestore configuration
    FIRESTORE_PROJECT_ID: str = Field(default="", description="GCP project ID for Firestore")

    GOOGLE_APPLICATION_CREDENTIALS: str = Field(
        default="", description="Path to GCP service account credentials JSON file"
    )

    # Service configuration
    PORT: int = Field(default=8080, description="Port to run the service on", ge=1, le=65535)

    SERVICE_NAME: str = Field(
        default="plan-scheduler", description="Name of the service for logging"
    )

    # Logging configuration
    LOG_LEVEL: str = Field(
        default="INFO",
        description=(
            "Logging level for the application. "
            "Valid values: DEBUG, INFO, WARNING, ERROR, CRITICAL. "
            "Invalid values will fall back to INFO with a warning."
        ),
    )

    # Runtime configuration for Cloud Run
    WORKERS: int = Field(
        default=1,
        description="Number of uvicorn worker processes. Defaults to 1 for Cloud Run.",
        ge=1,
        le=16,
    )

    # Pub/Sub configuration
    PUBSUB_VERIFICATION_TOKEN: str = Field(
        default="",
        description=(
            "Token for verifying Pub/Sub push requests. REQUIRED for security. "
            "This token should be sent by Pub/Sub in the x-goog-pubsub-verification-token header."
        ),
    )

    PUBSUB_JWT_VERIFICATION_ENABLED: bool = Field(
        default=False,
        description=(
            "Enable JWT verification for Pub/Sub push requests. "
            "When enabled, verifies JWT tokens in addition to the verification token."
        ),
    )

    # Execution service configuration
    EXECUTION_ENABLED: bool = Field(
        default=True, description="Enable or disable execution service triggers"
    )

    # External execution API configuration (placeholders for future integration)
    EXECUTION_API_URL: str = Field(
        default="",
        description=(
            "Base URL for external execution API. "
            "Leave empty if not using external execution service."
        ),
    )

    EXECUTION_API_KEY: str = Field(
        default="",
        description=(
            "API key for external execution service authentication. "
            "Leave empty if not using external execution service."
        ),
    )

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate and normalize LOG_LEVEL, falling back to INFO if invalid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = v.upper().strip()

        if normalized not in valid_levels:
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Invalid LOG_LEVEL '{v}' provided. Must be one of {valid_levels}. "
                f"Falling back to 'INFO'."
            )
            return "INFO"

        return normalized

    def model_post_init(self, __context):
        """Validate critical configuration and fail fast if required values are missing."""
        logger = logging.getLogger(__name__)

        if not self.FIRESTORE_PROJECT_ID:
            logger.warning(
                "FIRESTORE_PROJECT_ID not set, using empty string as default. "
                "Firestore operations may fail."
            )

        if not self.GOOGLE_APPLICATION_CREDENTIALS:
            logger.warning(
                "GOOGLE_APPLICATION_CREDENTIALS not set, using empty string as default. "
                "GCP authentication may fail."
            )

        # Fail fast if PUBSUB_VERIFICATION_TOKEN is unset or empty
        if not self.PUBSUB_VERIFICATION_TOKEN or not self.PUBSUB_VERIFICATION_TOKEN.strip():
            raise ValueError(
                "PUBSUB_VERIFICATION_TOKEN is required but not set or empty. "
                "The service cannot start without a verification token for "
                "securing Pub/Sub endpoints. "
                "Set this environment variable to a secure random token."
            )


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
