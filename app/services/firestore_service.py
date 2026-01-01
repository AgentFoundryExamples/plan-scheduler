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
"""Firestore service integration with credential-aware initialization.

This module provides:
1. Firestore client initialization and connectivity testing
2. Plan persistence with idempotent ingestion and conflict detection
3. Atomic batch writes for plan metadata and spec subcollections

Key Functions:
- get_client(): Get singleton Firestore client instance
- smoke_test(): Test Firestore connectivity
- create_plan_with_specs(): Create plan with specs (idempotent, atomic)

Exception Classes:
- FirestoreConfigurationError: Invalid or missing configuration
- FirestoreConnectionError: Connectivity test failures
- FirestoreOperationError: Firestore operation failures
- PlanConflictError: Plan exists with different body (includes digests)

Outcomes:
- PlanIngestionOutcome.CREATED: New plan created
- PlanIngestionOutcome.IDENTICAL: Idempotent success (same payload)
- PlanIngestionOutcome.CONFLICT: Raises PlanConflictError

Plan Structure:
- plans/{plan_id}: Metadata document
  - overall_status, total_specs, completed_specs, current_spec_index
  - last_event_at, raw_request, timestamps
- plans/{plan_id}/specs/{index}: Spec subcollection
  - status: "running" (index 0), "blocked" (others)
  - purpose, vision, must, dont, nice, assumptions
  - timestamps, history
"""

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

# Constants for execution metadata initialization
INITIAL_EXECUTION_ATTEMPT_COUNT = 1


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
            # An existing document should never be empty. This indicates an anomaly.
            raise FirestoreOperationError(f"Plan document {plan_id} exists but is empty.")

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
    except FirestoreOperationError:
        # Re-raise operation errors (including empty document error)
        raise
    except gcp_exceptions.GoogleAPICallError as e:
        error_msg = f"Firestore API error checking plan {plan_id}: {str(e)}"
        logger.error(error_msg)
        raise FirestoreOperationError(error_msg) from e


def delete_plan_with_specs(plan_id: str, client: firestore.Client | None = None) -> None:
    """
    Delete a plan document and all its specs subcollection from Firestore.

    This function is used for cleanup/rollback when plan ingestion partially succeeds
    but subsequent operations (like execution triggering) fail. It ensures that
    failed ingestions don't leave partial data in Firestore.

    CLEANUP STRATEGY:
    Uses batch operations instead of transactions to avoid read-before-write
    limitations. First reads all spec documents, then deletes them along with
    the plan document in a single batch. While not strictly transactional,
    this approach is suitable for cleanup scenarios where partial deletion
    is acceptable (the plan will be recreated on retry anyway).

    Args:
        plan_id: The plan ID to delete
        client: Optional Firestore client (uses get_client() if not provided)

    Raises:
        FirestoreOperationError: When Firestore operation fails
    """
    if client is None:
        client = get_client()

    try:
        # Read all spec documents first (outside batch)
        doc_ref = client.collection("plans").document(plan_id)
        specs_collection = doc_ref.collection("specs")
        spec_docs = list(specs_collection.stream())

        # Use batch to delete all documents
        batch = client.batch()

        # Delete all spec documents
        for spec_doc in spec_docs:
            batch.delete(spec_doc.reference)

        # Delete the plan document
        batch.delete(doc_ref)

        # Commit the batch
        batch.commit()
        logger.info(f"Deleted plan {plan_id} with all specs for cleanup")
    except gcp_exceptions.GoogleAPICallError as e:
        error_msg = f"Firestore API error deleting plan {plan_id}: {str(e)}"
        logger.error(error_msg)
        raise FirestoreOperationError(error_msg) from e


def create_plan_with_specs(
    plan_in: PlanIn,
    client: firestore.Client | None = None,
    trigger_first_spec: bool = True,
) -> tuple[PlanIngestionOutcome, str]:
    """
    Create a plan document with specs subcollection in Firestore.

    This function implements idempotent plan ingestion:
    - If plan doesn't exist, creates it with specs
    - If plan exists with identical payload, returns idempotent success
    - If plan exists with different payload, raises conflict error

    EXECUTION TRIGGER INTEGRATION:
    When trigger_first_spec is True (default), the first spec (index 0) is created
    with status="running" and execution metadata (execution_attempts=
    INITIAL_EXECUTION_ATTEMPT_COUNT, last_execution_at=now). This prepares spec 0
    for immediate execution triggering by the caller. All other specs remain
    "blocked" with zero attempts.

    TRANSACTIONAL ORDERING STRATEGY:
    Uses Firestore transactions to ensure atomicity - all writes succeed or fail
    together, and existence checks are atomic. The caller is responsible for:
    1. Calling this function to persist plan/specs
    2. Triggering execution for spec 0
    3. Calling delete_plan_with_specs() if execution trigger fails

    This ordering ensures cleanup is possible: if trigger fails after persistence,
    the caller can delete all docs. Plan IDs are scoped to avoid interference
    between concurrent ingestions.

    Plan metadata includes: overall_status="running", total_specs, completed_specs=0,
    current_spec_index=0, last_event_at, raw_request, and timestamps.

    Args:
        plan_in: PlanIn request payload
        client: Optional Firestore client (uses get_client() if not provided)
        trigger_first_spec: If True, set spec 0 metadata for execution (default: True)

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

    @firestore.transactional
    def create_in_transaction(transaction):
        """Transactional function to check and create plan atomically."""
        doc_ref = client.collection("plans").document(plan_id)
        doc_snapshot = doc_ref.get(transaction=transaction)

        # Check if plan exists within transaction
        if doc_snapshot.exists:
            doc_data = doc_snapshot.to_dict()
            if not doc_data:
                # An existing document should never be empty. This indicates an anomaly.
                raise FirestoreOperationError(f"Plan document {plan_id} exists but is empty.")

            # Get stored raw_request, fall back to comparing serialized specs if missing
            stored_raw_request = doc_data.get("raw_request")
            if not stored_raw_request:
                # Fall back to reconstructing from stored specs for old documents
                logger.warning(
                    f"Plan {plan_id} missing raw_request field, "
                    "falling back to spec count comparison"
                )
                stored_total_specs = doc_data.get("total_specs", 0)
                incoming_total_specs = len(plan_in.specs)
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
                logger.info(
                    f"Plan {plan_id} already exists with identical spec count, "
                    "skipping duplicate ingestion (legacy document without raw_request)"
                )
                return PlanIngestionOutcome.IDENTICAL

            # Compare digests of raw requests
            incoming_raw_request = plan_in.model_dump()
            stored_digest = _compute_request_digest(stored_raw_request)
            incoming_digest = _compute_request_digest(incoming_raw_request)

            if stored_digest == incoming_digest:
                logger.info(
                    f"Plan {plan_id} already exists with identical payload, "
                    "skipping duplicate ingestion"
                )
                return PlanIngestionOutcome.IDENTICAL

            # Requests differ - conflict
            raise PlanConflictError(
                f"Plan {plan_id} already exists with different body",
                stored_digest=stored_digest,
                incoming_digest=incoming_digest,
            )

        # Plan doesn't exist - create it
        now = datetime.now(UTC)

        # Create plan record
        plan_record = create_initial_plan_record(plan_in, overall_status="running", now=now)

        # Set current_spec_index to 0 since first spec will be running
        plan_record.current_spec_index = 0

        # Convert plan record to dict for Firestore
        plan_data = plan_record.model_dump(mode="json")
        transaction.create(doc_ref, plan_data)

        # Create spec documents in subcollection
        for idx, spec_in in enumerate(plan_in.specs):
            # First spec is running, rest are blocked
            status = "running" if idx == 0 else "blocked"
            spec_record = create_initial_spec_record(
                spec_in, spec_index=idx, status=status, now=now
            )

            # For spec 0 when trigger_first_spec is True, set execution metadata
            # to indicate it's ready for immediate execution trigger
            if idx == 0 and trigger_first_spec:
                spec_record.execution_attempts = INITIAL_EXECUTION_ATTEMPT_COUNT
                spec_record.last_execution_at = now

            # Use string index as document ID
            spec_doc_ref = doc_ref.collection("specs").document(str(idx))
            spec_data = spec_record.model_dump(mode="json")
            transaction.create(spec_doc_ref, spec_data)

        return PlanIngestionOutcome.CREATED

    # Execute the transaction
    try:
        transaction = client.transaction()
        outcome = create_in_transaction(transaction)

        if outcome == PlanIngestionOutcome.CREATED:
            logger.info(
                f"Created plan {plan_id} with {len(plan_in.specs)} specs "
                f"(first spec running, others blocked)"
            )

        return outcome, plan_id

    except (PlanConflictError, FirestoreOperationError):
        # Re-raise our custom errors
        raise
    except gcp_exceptions.GoogleAPICallError as e:
        error_msg = f"Firestore API error creating plan {plan_id}: {str(e)}"
        logger.error(error_msg)
        raise FirestoreOperationError(error_msg) from e


def process_spec_status_update(
    plan_id: str,
    spec_index: int,
    status: str,
    stage: str | None,
    message_id: str,
    raw_payload_snippet: dict[str, Any],
    details: str | None = None,
    correlation_id: str | None = None,
    timestamp: str | None = None,
    client: firestore.Client | None = None,
) -> dict[str, Any]:
    """
    Process a spec status update transactionally.

    This function implements the core orchestration logic for Pub/Sub status updates:
    1. Load plan and target spec within a transaction
    2. Verify ordering (detect out-of-order or stale terminal events)
    3. Check for duplicate messageIds to prevent double-processing
    4. Append status history entry with timestamp, status, stage, details,
       correlation_id, messageId, raw snippet
    5. Update spec and plan fields based on status type:
       - "finished": Mark spec finished, advance plan, trigger next spec (terminal)
       - "failed": Mark spec/plan failed, no further triggers (terminal)
       - All other statuses: Update stage field, keep main status unchanged (informational)

    Terminal vs Informational Statuses:
    - Terminal statuses ("finished", "failed") trigger state machine transitions
    - All other status values are informational and stored in history without
      changing the spec's main status field or triggering transitions

    TRANSACTION STRATEGY:
    Uses Firestore transactions to ensure atomicity. All reads must happen before writes.
    The transaction will retry automatically on contention.

    ORDERING VALIDATION:
    - Detects if a later spec finishes before an earlier spec
    - Detects duplicate terminal statuses (finished/failed after already terminal)
    - Aborts transaction and logs errors for invalid ordering

    Args:
        plan_id: Plan ID as UUID string
        spec_index: Zero-based index of the spec
        status: New status value (any string, "finished" and "failed" are terminal)
        stage: Optional execution stage/phase information
        message_id: Pub/Sub message ID for deduplication
        raw_payload_snippet: Snippet of raw payload for history
        details: Optional additional details about the status update
        correlation_id: Optional correlation ID for tracking related events
        timestamp: Optional timestamp for when this status occurred (ISO 8601 format)
        client: Optional Firestore client (uses get_client() if not provided)

    Returns:
        Dictionary with processing result:
        {
            "success": True/False,
            "action": "updated"/"duplicate"/"out_of_order"/"not_found",
            "next_spec_triggered": True/False (only for finished status),
            "plan_finished": True/False (only when plan completes),
            "message": "descriptive message"
        }

    Raises:
        FirestoreOperationError: When Firestore operation fails
    """
    if client is None:
        client = get_client()

    result = {
        "success": False,
        "action": "unknown",
        "next_spec_triggered": False,
        "plan_finished": False,
        "message": "",
    }

    @firestore.transactional
    def update_in_transaction(transaction):
        """Transactional function to update plan and spec atomically."""
        nonlocal result
        now = datetime.now(UTC)

        # Step 1: Load plan document
        plan_ref = client.collection("plans").document(plan_id)
        plan_snapshot = plan_ref.get(transaction=transaction)

        if not plan_snapshot.exists:
            result["action"] = "not_found"
            result["message"] = f"Plan {plan_id} not found"
            logger.warning(
                f"Plan {plan_id} not found during status update",
                extra={"plan_id": plan_id, "spec_index": spec_index, "status": status},
            )
            return

        plan_data = plan_snapshot.to_dict()
        if not plan_data:
            raise FirestoreOperationError(f"Plan document {plan_id} exists but is empty")

        # Step 2: Load spec document
        spec_ref = plan_ref.collection("specs").document(str(spec_index))
        spec_snapshot = spec_ref.get(transaction=transaction)

        if not spec_snapshot.exists:
            result["action"] = "not_found"
            result["message"] = f"Spec {spec_index} not found in plan {plan_id}"
            logger.warning(
                f"Spec {spec_index} not found in plan {plan_id}",
                extra={"plan_id": plan_id, "spec_index": spec_index, "status": status},
            )
            return

        spec_data = spec_snapshot.to_dict()
        if not spec_data:
            raise FirestoreOperationError(
                f"Spec document {plan_id}/specs/{spec_index} exists but is empty"
            )

        # Step 3: Check for duplicate messageId
        history = spec_data.get("history", [])
        for entry in history:
            if entry.get("message_id") == message_id:
                result["action"] = "duplicate"
                result["success"] = True
                result["message"] = f"Duplicate message {message_id} skipped"
                logger.info(
                    f"Duplicate Pub/Sub message {message_id} detected for "
                    f"plan {plan_id} spec {spec_index}, skipping",
                    extra={
                        "plan_id": plan_id,
                        "spec_index": spec_index,
                        "message_id": message_id,
                    },
                )
                return

        # Step 4: Validate ordering for terminal statuses
        current_spec_status = spec_data.get("status")
        is_terminal_status = status in ["finished", "failed"]
        is_already_terminal = current_spec_status in ["finished", "failed"]

        # Detect duplicate terminal status on same spec
        if is_terminal_status and is_already_terminal:
            result["action"] = "out_of_order"
            result["message"] = (
                f"Spec {spec_index} already in terminal state {current_spec_status}, "
                f"ignoring {status} status"
            )
            logger.warning(
                f"Out-of-order terminal status for plan {plan_id} spec {spec_index}: "
                f"already {current_spec_status}, received {status}",
                extra={
                    "plan_id": plan_id,
                    "spec_index": spec_index,
                    "current_status": current_spec_status,
                    "received_status": status,
                    "message_id": message_id,
                },
            )
            return

        # Detect out-of-order spec finishing (only for "finished" status)
        # Only the current spec should be allowed to finish
        if status == "finished":
            current_spec_index = plan_data.get("current_spec_index")
            if current_spec_index is not None and spec_index != current_spec_index:
                result["action"] = "out_of_order"
                result["message"] = (
                    f"Spec {spec_index} finishing out of order. "
                    f"Expected current spec is {current_spec_index}."
                )
                logger.error(
                    f"Out-of-order spec completion detected: spec {spec_index} finishing "
                    f"while current spec is {current_spec_index} in plan {plan_id}",
                    extra={
                        "plan_id": plan_id,
                        "spec_index": spec_index,
                        "current_spec_index": current_spec_index,
                        "status": status,
                        "message_id": message_id,
                    },
                )
                return

        # Step 5: Create history entry with all fields
        # Use provided timestamp if available, otherwise use current time
        history_entry = {
            "timestamp": timestamp or now.isoformat(),
            "received_status": status,
            "stage": stage,
            "details": details,
            "correlation_id": correlation_id,
            "raw_snippet": raw_payload_snippet,
            "message_id": message_id,
        }
        history.append(history_entry)

        # Step 6: Determine updates based on status type
        spec_updates = {
            "updated_at": now,
            "history": history,
        }

        plan_updates = {
            "updated_at": now,
            "last_event_at": now,
        }

        if status == "finished":
            # Mark spec as finished
            spec_updates["status"] = "finished"

            # Update plan counters
            completed_specs = plan_data.get("completed_specs", 0) + 1
            total_specs = plan_data.get("total_specs", 0)
            plan_updates["completed_specs"] = completed_specs

            # Check if this is the last spec
            if completed_specs >= total_specs:
                # Plan is finished
                plan_updates["overall_status"] = "finished"
                plan_updates["current_spec_index"] = None
                result["plan_finished"] = True
                result["message"] = f"Plan {plan_id} marked as finished"
                logger.info(
                    f"Plan {plan_id} completed: all {total_specs} specs finished",
                    extra={
                        "plan_id": plan_id,
                        "total_specs": total_specs,
                        "completed_specs": completed_specs,
                    },
                )
            else:
                # Advance to next spec
                next_spec_index = spec_index + 1
                plan_updates["current_spec_index"] = next_spec_index

                # Unblock next spec (blocked -> running)
                next_spec_ref = plan_ref.collection("specs").document(str(next_spec_index))
                next_spec_snapshot = next_spec_ref.get(transaction=transaction)

                if next_spec_snapshot.exists:
                    next_spec_data = next_spec_snapshot.to_dict()
                    if next_spec_data and next_spec_data.get("status") == "blocked":
                        next_spec_updates = {
                            "status": "running",
                            "updated_at": now,
                        }
                        transaction.update(next_spec_ref, next_spec_updates)
                        result["next_spec_triggered"] = True
                        result["message"] = (
                            f"Spec {spec_index} finished, spec {next_spec_index} unblocked"
                        )
                        logger.info(
                            f"Spec {next_spec_index} unblocked in plan {plan_id}",
                            extra={
                                "plan_id": plan_id,
                                "spec_index": next_spec_index,
                                "previous_spec": spec_index,
                            },
                        )
                    else:
                        result["message"] = f"Spec {spec_index} finished"
                        current_status = (
                            next_spec_data.get("status") if next_spec_data else "unknown"
                        )
                        logger.info(
                            f"Next spec {next_spec_index} in plan {plan_id} is not blocked, "
                            f"skipping unblock (current status: {current_status})",
                            extra={
                                "plan_id": plan_id,
                                "spec_index": next_spec_index,
                                "status": next_spec_data.get("status") if next_spec_data else None,
                            },
                        )
                else:
                    result["message"] = f"Spec {spec_index} finished"
                    logger.warning(
                        f"Next spec {next_spec_index} not found in plan {plan_id}",
                        extra={"plan_id": plan_id, "spec_index": next_spec_index},
                    )

        elif status == "failed":
            # Mark spec as failed
            spec_updates["status"] = "failed"

            # Mark plan as failed
            plan_updates["overall_status"] = "failed"
            result["message"] = f"Spec {spec_index} and plan {plan_id} marked as failed"
            logger.info(
                f"Spec {spec_index} failed in plan {plan_id}, plan marked as failed",
                extra={"plan_id": plan_id, "spec_index": spec_index, "status": status},
            )

        else:
            # Intermediate status - update stage field but keep main status unchanged
            if stage:
                spec_updates["current_stage"] = stage
            result["message"] = f"Spec {spec_index} stage updated: {stage if stage else 'none'}"
            logger.info(
                f"Intermediate status update for spec {spec_index} in plan {plan_id}",
                extra={
                    "plan_id": plan_id,
                    "spec_index": spec_index,
                    "status": status,
                    "stage": stage,
                },
            )

        # Step 7: Write updates
        transaction.update(spec_ref, spec_updates)
        transaction.update(plan_ref, plan_updates)

        result["success"] = True
        result["action"] = "updated"

    # Execute the transaction
    try:
        transaction = client.transaction()
        update_in_transaction(transaction)
        return result

    except FirestoreOperationError:
        # Re-raise our custom errors
        raise
    except gcp_exceptions.GoogleAPICallError as e:
        error_msg = (
            f"Firestore API error processing status update for plan {plan_id} "
            f"spec {spec_index}: {str(e)}"
        )
        logger.error(error_msg)
        raise FirestoreOperationError(error_msg) from e


def get_plan_with_specs(
    plan_id: str, client: firestore.Client | None = None
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """
    Fetch a plan document and all its specs in an efficient manner.

    This function retrieves the plan metadata and all spec documents using
    a single query for specs ordered by spec_index ascending. It does NOT
    include heavy fields like history or raw_request in the return values.

    Args:
        plan_id: The plan ID to fetch
        client: Optional Firestore client (uses get_client() if not provided)

    Returns:
        Tuple of (plan_data, spec_list)
        - plan_data: Dictionary of plan fields, or None if plan not found
        - spec_list: List of spec dictionaries sorted by spec_index (empty list if plan not found)

    Raises:
        FirestoreOperationError: When Firestore operation fails
    """
    if client is None:
        client = get_client()

    try:
        # Fetch plan document
        plan_ref = client.collection("plans").document(plan_id)
        plan_snapshot = plan_ref.get()

        if not plan_snapshot.exists:
            logger.info(f"Plan {plan_id} not found")
            return None, []

        plan_data = plan_snapshot.to_dict()
        if not plan_data:
            raise FirestoreOperationError(f"Plan document {plan_id} exists but is empty")

        # Fetch all spec documents ordered by spec_index
        # Firestore composite indexes are NOT required for subcollection queries
        # that only sort on a single field within the subcollection
        specs_ref = plan_ref.collection("specs")
        specs_query = specs_ref.order_by("spec_index", direction=firestore.Query.ASCENDING)
        spec_docs = list(specs_query.stream())

        # Extract spec data from documents (filtering ensures we only get valid specs)
        spec_list = [spec_doc.to_dict() for spec_doc in spec_docs if spec_doc.to_dict()]

        logger.info(
            f"Fetched plan {plan_id} with {len(spec_list)} specs",
            extra={"plan_id": plan_id, "spec_count": len(spec_list)},
        )

        return plan_data, spec_list

    except gcp_exceptions.GoogleAPICallError as e:
        error_msg = f"Firestore API error fetching plan {plan_id}: {str(e)}"
        logger.error(error_msg)
        raise FirestoreOperationError(error_msg) from e
