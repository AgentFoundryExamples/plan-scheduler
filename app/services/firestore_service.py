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

import logging
import uuid
from functools import lru_cache

from google.api_core import exceptions as gcp_exceptions
from google.auth import exceptions as auth_exceptions
from google.cloud import firestore

from app.config import get_settings

logger = logging.getLogger(__name__)


class FirestoreConfigurationError(Exception):
    """Raised when Firestore configuration is invalid or missing."""

    pass


class FirestoreConnectionError(Exception):
    """Raised when Firestore connectivity test fails."""

    pass


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
