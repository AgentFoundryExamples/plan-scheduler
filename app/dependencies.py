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
"""Shared dependencies for dependency injection."""

from google.cloud import firestore

from app.config import Settings, get_settings
from app.services import firestore_service


def get_cached_settings() -> Settings:
    """
    Get cached settings instance for dependency injection.

    This wraps get_settings() which is already cached with @lru_cache.
    """
    return get_settings()


def get_firestore_client() -> firestore.Client:
    """
    Get cached Firestore client instance for dependency injection.

    This wraps firestore_service.get_client() which is already cached
    with @lru_cache to ensure singleton semantics.

    Returns:
        firestore.Client: Cached Firestore client instance

    Raises:
        firestore_service.FirestoreConfigurationError: If configuration is invalid
    """
    return firestore_service.get_client()
