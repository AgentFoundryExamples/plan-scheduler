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
            "Token for verifying Pub/Sub push requests. "
            "Used as fallback when OIDC authentication is not configured. "
            "This token should be sent by Pub/Sub in the x-goog-pubsub-verification-token header."
        ),
    )

    PUBSUB_OIDC_ENABLED: bool = Field(
        default=True,
        description=(
            "Enable OIDC JWT verification for Pub/Sub push requests. "
            "When enabled, validates Google-signed JWT tokens from Authorization header. "
            "Falls back to PUBSUB_VERIFICATION_TOKEN if disabled or when JWT validation fails."
        ),
    )

    PUBSUB_EXPECTED_AUDIENCE: str = Field(
        default="",
        description=(
            "Expected audience claim in OIDC JWT tokens from Pub/Sub. "
            "Typically the Cloud Run service URL. Required when PUBSUB_OIDC_ENABLED is True. "
            "Example: https://plan-scheduler-abc123-uc.a.run.app"
        ),
    )

    PUBSUB_EXPECTED_ISSUER: str = Field(
        default="https://accounts.google.com",
        description=(
            "Expected issuer claim in OIDC JWT tokens from Pub/Sub. "
            "Default is Google's issuer for service account tokens."
        ),
    )

    PUBSUB_SERVICE_ACCOUNT_EMAIL: str = Field(
        default="",
        description=(
            "Expected service account email in JWT subject claim. "
            "Should match the Pub/Sub push subscription service account. "
            "Optional but recommended for enhanced security."
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
            # Use print for validation warnings since logging may not be configured yet
            import sys

            print(
                f"WARNING: Invalid LOG_LEVEL '{v}' provided. "
                f"Must be one of {valid_levels}. Falling back to 'INFO'.",
                file=sys.stderr,
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

        # Validate Pub/Sub authentication configuration
        if self.PUBSUB_OIDC_ENABLED:
            # When OIDC is enabled, require audience
            if not self.PUBSUB_EXPECTED_AUDIENCE or not self.PUBSUB_EXPECTED_AUDIENCE.strip():
                logger.warning(
                    "PUBSUB_OIDC_ENABLED is True but PUBSUB_EXPECTED_AUDIENCE is not set. "
                    "OIDC validation will fail. Set PUBSUB_EXPECTED_AUDIENCE to your "
                    "Cloud Run service URL or disable OIDC by setting PUBSUB_OIDC_ENABLED=False."
                )
            # Shared token becomes optional when OIDC is enabled
            if not self.PUBSUB_VERIFICATION_TOKEN or not self.PUBSUB_VERIFICATION_TOKEN.strip():
                logger.info(
                    "PUBSUB_VERIFICATION_TOKEN not set. Relying solely on OIDC authentication. "
                    "Shared token fallback will not be available."
                )
        else:
            # When OIDC is disabled, require shared token
            if not self.PUBSUB_VERIFICATION_TOKEN or not self.PUBSUB_VERIFICATION_TOKEN.strip():
                raise ValueError(
                    "PUBSUB_VERIFICATION_TOKEN is required when PUBSUB_OIDC_ENABLED is False. "
                    "The service cannot start without authentication for Pub/Sub endpoints. "
                    "Set PUBSUB_VERIFICATION_TOKEN or enable OIDC with PUBSUB_OIDC_ENABLED=True."
                )


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
