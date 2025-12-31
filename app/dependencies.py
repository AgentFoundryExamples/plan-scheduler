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
from app.models.plan import PlanIn
from app.services import firestore_service
from app.services.firestore_service import PlanIngestionOutcome


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


def create_plan(plan_in: PlanIn) -> tuple[PlanIngestionOutcome, str]:
    """
    Create a plan with specs in Firestore (dependency injection wrapper).

    This wraps firestore_service.create_plan_with_specs() for use in FastAPI
    dependency injection. Uses the cached Firestore client.

    Args:
        plan_in: PlanIn request payload

    Returns:
        Tuple of (outcome, plan_id)

    Raises:
        firestore_service.PlanConflictError: When plan exists with different body
        firestore_service.FirestoreOperationError: When Firestore operation fails
    """
    return firestore_service.create_plan_with_specs(plan_in)
