"""Application configuration using pydantic BaseSettings."""

import logging
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # Firestore configuration
    FIRESTORE_PROJECT_ID: str = Field(
        default="",
        description="GCP project ID for Firestore"
    )
    
    GOOGLE_APPLICATION_CREDENTIALS: str = Field(
        default="",
        description="Path to GCP service account credentials JSON file"
    )
    
    # Service configuration
    PORT: int = Field(
        default=8080,
        description="Port to run the service on",
        ge=1,
        le=65535
    )
    
    SERVICE_NAME: str = Field(
        default="plan-scheduler",
        description="Name of the service for logging"
    )
    
    # Pub/Sub configuration
    PUBSUB_VERIFICATION_TOKEN: str = Field(
        default="",
        description="Token for verifying Pub/Sub requests"
    )

    def model_post_init(self, __context):
        """Log warnings for missing critical configuration after initialization."""
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
        
        if not self.PUBSUB_VERIFICATION_TOKEN:
            logger.warning(
                "PUBSUB_VERIFICATION_TOKEN not set, using empty string as default. "
                "Pub/Sub request verification will be disabled."
            )


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
