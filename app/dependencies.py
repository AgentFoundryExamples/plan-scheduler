"""Shared dependencies for dependency injection."""

from functools import lru_cache

from app.config import Settings, get_settings


@lru_cache()
def get_cached_settings() -> Settings:
    """
    Get cached settings instance for dependency injection.
    
    Uses lru_cache to ensure settings are loaded only once
    and reused across requests.
    """
    return get_settings()
