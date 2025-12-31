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

import logging

from google.cloud import firestore

from app.config import Settings, get_settings
from app.models.plan import PlanIn
from app.services import firestore_service
from app.services.execution_service import ExecutionService
from app.services.firestore_service import PlanIngestionOutcome

logger = logging.getLogger(__name__)


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


def get_execution_service() -> ExecutionService:
    """
    Get ExecutionService instance for dependency injection.

    Returns:
        ExecutionService: Execution service instance for triggering spec execution
    """
    return ExecutionService()


def create_plan(plan_in: PlanIn) -> tuple[PlanIngestionOutcome, str]:
    """
    Create a plan with specs in Firestore and trigger execution for spec 0.

    ORCHESTRATION AND CLEANUP STRATEGY:
    This function orchestrates the complete plan ingestion flow:
    1. Persist plan and specs to Firestore (with spec 0 status="running")
    2. Trigger execution for spec 0 (if EXECUTION_ENABLED and outcome is CREATED)
    3. If trigger fails, delete all persisted documents for cleanup

    The ordering guarantees clean rollback: we can only delete docs that were
    successfully created. Plan IDs are scoped, so concurrent ingestions don't
    interfere with each other's cleanup operations.

    EXECUTION TOGGLE BEHAVIOR:
    - When EXECUTION_ENABLED=True: Trigger execution for newly created plans
    - When EXECUTION_ENABLED=False: Skip trigger but still persist spec 0 as "running"
      with execution metadata set (this maintains deterministic status for testing)

    IDEMPOTENCY:
    - For idempotent ingestions (identical payload), we skip execution triggering
      entirely since the plan was already processed on the original ingestion

    Args:
        plan_in: PlanIn request payload

    Returns:
        Tuple of (outcome, plan_id)

    Raises:
        firestore_service.PlanConflictError: When plan exists with different body
        firestore_service.FirestoreOperationError: When Firestore operation fails
        Exception: When execution trigger fails (after cleanup is attempted)
    """
    settings = get_cached_settings()
    execution_service = get_execution_service()
    client = get_firestore_client()

    # Step 1: Persist plan and specs to Firestore
    # The first spec (index 0) is persisted with status="running",
    # execution_attempts=1, and last_execution_at set
    outcome, plan_id = firestore_service.create_plan_with_specs(
        plan_in, client=client, trigger_first_spec=True
    )

    # Step 2: For idempotent ingestions, skip execution trigger
    # (plan was already processed on original ingestion)
    if outcome == PlanIngestionOutcome.IDENTICAL:
        logger.info(
            f"Skipping execution trigger for idempotent ingestion of plan {plan_id}"
        )
        return outcome, plan_id

    # Step 3: For new plans, attempt to trigger execution for spec 0
    # If EXECUTION_ENABLED is False, the trigger is logged but skipped
    # If trigger raises an exception, we clean up the persisted plan/specs
    try:
        if settings.EXECUTION_ENABLED:
            logger.info(
                f"Triggering execution for spec 0 of plan {plan_id}",
                extra={"plan_id": plan_id, "spec_index": 0},
            )
            # Get spec 0 data for triggering (we just created it)
            spec_doc = client.collection("plans").document(plan_id).collection("specs").document("0").get()
            if not spec_doc.exists:
                raise firestore_service.FirestoreOperationError(
                    f"Spec 0 not found after creation for plan {plan_id}"
                )
            
            from app.models.plan import SpecRecord
            spec_data = SpecRecord(**spec_doc.to_dict())
            
            execution_service.trigger_spec_execution(
                plan_id=plan_id,
                spec_index=0,
                spec_data=spec_data,
            )
        else:
            logger.info(
                f"Execution disabled, skipping trigger for spec 0 of plan {plan_id}",
                extra={
                    "plan_id": plan_id,
                    "spec_index": 0,
                    "execution_enabled": False,
                },
            )
    except Exception as e:
        # Step 4: CLEANUP - If execution trigger fails, delete all persisted documents
        # This ensures failed ingestions don't leave partial data
        logger.error(
            f"Execution trigger failed for plan {plan_id}, initiating cleanup",
            extra={
                "plan_id": plan_id,
                "spec_index": 0,
                "error": str(e),
            },
            exc_info=True,
        )
        try:
            firestore_service.delete_plan_with_specs(plan_id, client=client)
            logger.info(f"Cleanup completed for plan {plan_id}")
        except Exception as cleanup_error:
            # Log cleanup failure but don't mask the original error
            logger.error(
                f"Cleanup failed for plan {plan_id} after execution trigger failure",
                extra={
                    "plan_id": plan_id,
                    "cleanup_error": str(cleanup_error),
                    "original_error": str(e),
                },
                exc_info=True,
            )
        # Re-raise the original error to propagate failure to API layer
        raise

    return outcome, plan_id
