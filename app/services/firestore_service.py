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
"""Firestore service integration with credential-aware initialization."""

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from enum import Enum
from functools import lru_cache
from typing import Any

from google.api_core import exceptions as gcp_exceptions
from google.auth import exceptions as auth_exceptions
from google.cloud import firestore

from app.config import get_settings
from app.models.plan import PlanIn, create_initial_plan_record, create_initial_spec_record

logger = logging.getLogger(__name__)


class FirestoreConfigurationError(Exception):
    """Raised when Firestore configuration is invalid or missing."""

    pass


class FirestoreConnectionError(Exception):
    """Raised when Firestore connectivity test fails."""

    pass


class FirestoreOperationError(Exception):
    """Raised when Firestore operation fails."""

    pass


class PlanConflictError(Exception):
    """Raised when plan already exists with different body."""

    def __init__(self, message: str, stored_digest: str, incoming_digest: str):
        super().__init__(message)
        self.stored_digest = stored_digest
        self.incoming_digest = incoming_digest


class PlanIngestionOutcome(str, Enum):
    """Outcome of plan ingestion operation."""

    CREATED = "created"
    IDENTICAL = "identical"
    CONFLICT = "conflict"


@lru_cache(maxsize=1)
def get_client() -> firestore.Client:
    """
    Get a singleton Firestore client instance.

    Uses Application Default Credentials (ADC) and the FIRESTORE_PROJECT_ID
    from settings to initialize the client. The client is cached using
    @lru_cache to ensure only one instance exists.

    Returns:
        firestore.Client: Initialized Firestore client

    Raises:
        FirestoreConfigurationError: If FIRESTORE_PROJECT_ID is not configured
        FirestoreConfigurationError: If Application Default Credentials are not available
    """
    settings = get_settings()

    # Validate that FIRESTORE_PROJECT_ID is configured
    if not settings.FIRESTORE_PROJECT_ID:
        raise FirestoreConfigurationError(
            "FIRESTORE_PROJECT_ID is not configured. "
            "Please set the FIRESTORE_PROJECT_ID environment variable to your GCP project ID."
        )

    try:
        # Initialize Firestore client with ADC and project ID
        client = firestore.Client(project=settings.FIRESTORE_PROJECT_ID)
        logger.info(f"Firestore client initialized for project: {settings.FIRESTORE_PROJECT_ID}")
        return client
    except auth_exceptions.DefaultCredentialsError as e:
        raise FirestoreConfigurationError(
            "Application Default Credentials (ADC) not found. "
            "Please set GOOGLE_APPLICATION_CREDENTIALS environment variable to the path "
            "of your service account JSON key file, or run 'gcloud auth application-default login' "
            "for local development. "
            f"Original error: {str(e)}"
        ) from e
    except Exception as e:
        raise FirestoreConfigurationError(f"Failed to initialize Firestore client: {str(e)}") from e


def smoke_test(client: firestore.Client | None = None) -> None:
    """
    Perform a smoke test to verify Firestore connectivity.

    This function writes a test document to the 'plans_dev_test' collection,
    reads it back to verify connectivity, and then cleans up by deleting
    the test document. Uses a unique document ID to avoid concurrent test conflicts.

    Args:
        client: Optional Firestore client. If not provided, uses get_client()

    Raises:
        FirestoreConnectionError: If any operation fails (write, read, or delete)
    """
    if client is None:
        client = get_client()

    # Generate unique document ID to avoid race conditions in concurrent tests
    test_doc_id = f"test_{uuid.uuid4().hex}"
    test_collection = "plans_dev_test"
    test_data = {
        "test": True,
        "message": "Firestore connectivity test",
        "timestamp": firestore.SERVER_TIMESTAMP,
    }

    doc_ref = None

    try:
        # Write test document
        doc_ref = client.collection(test_collection).document(test_doc_id)
        doc_ref.set(test_data)
        logger.info(f"Smoke test: wrote test document {test_collection}/{test_doc_id}")

        # Read back test document to verify connectivity
        doc_snapshot = doc_ref.get()
        if not doc_snapshot.exists:
            raise FirestoreConnectionError(
                f"Smoke test failed: document {test_collection}/{test_doc_id} "
                "was not found after write"
            )

        # Verify the data
        retrieved_data = doc_snapshot.to_dict()
        if not retrieved_data or retrieved_data.get("test") is not True:
            raise FirestoreConnectionError(
                f"Smoke test failed: document data validation failed. "
                f"Expected test=True, got: {retrieved_data}"
            )

        logger.info(f"Smoke test: successfully read back document {test_collection}/{test_doc_id}")

    except gcp_exceptions.GoogleAPICallError as e:
        # Handle network errors, timeouts, permission errors
        error_msg = (
            f"Smoke test failed due to Firestore API error: {str(e)}. "
            f"This could be due to network issues, insufficient permissions, "
            f"or Firestore service unavailability."
        )
        logger.error(error_msg)
        raise FirestoreConnectionError(error_msg) from e
    except Exception as e:
        # Catch any other unexpected errors
        error_msg = f"Smoke test failed with unexpected error: {str(e)}"
        logger.error(error_msg)
        raise FirestoreConnectionError(error_msg) from e
    finally:
        # Always attempt cleanup, even if test failed
        if doc_ref is not None:
            try:
                doc_ref.delete()
                logger.info(f"Smoke test: cleaned up test document {test_collection}/{test_doc_id}")
            except Exception as cleanup_error:
                # Log cleanup failure but don't raise - original error is more important
                logger.warning(
                    f"Smoke test: failed to clean up test document "
                    f"{test_collection}/{test_doc_id}: {str(cleanup_error)}"
                )


def _compute_request_digest(raw_request: dict[str, Any]) -> str:
    """
    Compute a stable digest of a request payload for comparison.

    Args:
        raw_request: The request payload as a dictionary

    Returns:
        SHA-256 hex digest of the canonicalized JSON
    """
    # Sort keys for stable serialization
    canonical_json = json.dumps(raw_request, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _check_plan_exists(
    client: firestore.Client, plan_id: str, incoming_plan: PlanIn
) -> tuple[bool, PlanIngestionOutcome | None, str | None]:
    """
    Check if a plan document exists and compare with incoming plan.

    Args:
        client: Firestore client instance
        plan_id: Plan ID to check
        incoming_plan: Incoming PlanIn payload

    Returns:
        Tuple of (exists, outcome, stored_digest)
        - exists: True if plan document exists
        - outcome: IDENTICAL if requests match, CONFLICT if different, None if doesn't exist
        - stored_digest: Digest of stored raw_request, None if doesn't exist

    Raises:
        FirestoreOperationError: If Firestore operation fails
    """
    try:
        doc_ref = client.collection("plans").document(plan_id)
        doc_snapshot = doc_ref.get()

        if not doc_snapshot.exists:
            return False, None, None

        doc_data = doc_snapshot.to_dict()
        if not doc_data:
            return False, None, None

        # Get stored raw_request, fall back to comparing serialized specs if missing
        stored_raw_request = doc_data.get("raw_request")
        if not stored_raw_request:
            # Fall back to reconstructing from stored specs for old documents
            logger.warning(
                f"Plan {plan_id} missing raw_request field, "
                "falling back to spec count comparison"
            )
            stored_total_specs = doc_data.get("total_specs", 0)
            incoming_total_specs = len(incoming_plan.specs)
            if stored_total_specs != incoming_total_specs:
                # Different spec counts indicate conflict
                stored_digest = f"spec_count_{stored_total_specs}"
                incoming_digest = f"spec_count_{incoming_total_specs}"
                raise PlanConflictError(
                    f"Plan {plan_id} exists with different spec count",
                    stored_digest=stored_digest,
                    incoming_digest=incoming_digest,
                )
            # Same spec count, assume identical for idempotency
            return True, PlanIngestionOutcome.IDENTICAL, None

        # Compare digests of raw requests
        incoming_raw_request = incoming_plan.model_dump()
        stored_digest = _compute_request_digest(stored_raw_request)
        incoming_digest = _compute_request_digest(incoming_raw_request)

        if stored_digest == incoming_digest:
            return True, PlanIngestionOutcome.IDENTICAL, stored_digest

        # Requests differ - conflict
        raise PlanConflictError(
            f"Plan {plan_id} already exists with different body",
            stored_digest=stored_digest,
            incoming_digest=incoming_digest,
        )

    except PlanConflictError:
        # Re-raise conflict errors
        raise
    except gcp_exceptions.GoogleAPICallError as e:
        error_msg = f"Firestore API error checking plan {plan_id}: {str(e)}"
        logger.error(error_msg)
        raise FirestoreOperationError(error_msg) from e
    except Exception as e:
        error_msg = f"Unexpected error checking plan {plan_id}: {str(e)}"
        logger.error(error_msg)
        raise FirestoreOperationError(error_msg) from e


def create_plan_with_specs(
    plan_in: PlanIn, client: firestore.Client | None = None
) -> tuple[PlanIngestionOutcome, str]:
    """
    Create a plan document with specs subcollection in Firestore.

    This function implements idempotent plan ingestion:
    - If plan doesn't exist, creates it with specs
    - If plan exists with identical payload, returns idempotent success
    - If plan exists with different payload, raises conflict error

    The first spec (index 0) starts as "running", all others as "blocked".
    Plan metadata includes: overall_status="running", total_specs, completed_specs=0,
    current_spec_index=0, last_event_at, raw_request, and timestamps.

    Uses batch writes to ensure atomicity - all writes succeed or fail together.

    Args:
        plan_in: PlanIn request payload
        client: Optional Firestore client (uses get_client() if not provided)

    Returns:
        Tuple of (outcome, plan_id)
        - outcome: PlanIngestionOutcome.CREATED or IDENTICAL
        - plan_id: The plan ID

    Raises:
        PlanConflictError: When plan exists with different body
        FirestoreOperationError: When Firestore operation fails
    """
    if client is None:
        client = get_client()

    plan_id = plan_in.id

    # Check if plan already exists
    exists, outcome, _ = _check_plan_exists(client, plan_id, plan_in)

    if exists:
        if outcome == PlanIngestionOutcome.IDENTICAL:
            logger.info(
                f"Plan {plan_id} already exists with identical payload, "
                "skipping duplicate ingestion"
            )
            return PlanIngestionOutcome.IDENTICAL, plan_id
        # If we reach here, it means conflict was detected and exception was raised

    # Create new plan - use batch for atomicity
    try:
        batch = client.batch()
        now = datetime.now(UTC)

        # Create plan record
        plan_record = create_initial_plan_record(plan_in, overall_status="running", now=now)

        # Set current_spec_index to 0 since first spec will be running
        plan_record.current_spec_index = 0

        # Convert plan record to dict for Firestore
        plan_doc_ref = client.collection("plans").document(plan_id)
        plan_data = plan_record.model_dump(mode="json")
        batch.set(plan_doc_ref, plan_data)

        # Create spec documents in subcollection
        for idx, spec_in in enumerate(plan_in.specs):
            # First spec is running, rest are blocked
            status = "running" if idx == 0 else "blocked"
            spec_record = create_initial_spec_record(
                spec_in, spec_index=idx, status=status, now=now
            )

            # Use string index as document ID
            spec_doc_ref = plan_doc_ref.collection("specs").document(str(idx))
            spec_data = spec_record.model_dump(mode="json")
            batch.set(spec_doc_ref, spec_data)

        # Commit batch
        batch.commit()
        logger.info(
            f"Created plan {plan_id} with {len(plan_in.specs)} specs "
            f"(first spec running, others blocked)"
        )

        return PlanIngestionOutcome.CREATED, plan_id

    except gcp_exceptions.GoogleAPICallError as e:
        error_msg = f"Firestore API error creating plan {plan_id}: {str(e)}"
        logger.error(error_msg)
        raise FirestoreOperationError(error_msg) from e
    except Exception as e:
        error_msg = f"Unexpected error creating plan {plan_id}: {str(e)}"
        logger.error(error_msg)
        raise FirestoreOperationError(error_msg) from e
