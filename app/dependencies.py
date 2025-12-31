"""Shared dependencies for dependency injection."""

from app.config import Settings, get_settings


def get_cached_settings() -> Settings:
    """
    Get cached settings instance for dependency injection.
    
    This wraps get_settings() which is already cached with @lru_cache.
    """
    return get_settings()
