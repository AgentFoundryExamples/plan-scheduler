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
"""Health check endpoint."""

import logging

from fastapi import APIRouter, Response, status

from app.dependencies import get_firestore_client

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check() -> dict:
    """
    Basic health check endpoint.

    Returns a simple OK status without performing any expensive operations.
    Suitable for basic health monitoring.

    Returns:
        dict: Status indicating service is healthy
    """
    return {"status": "ok"}


@router.get("/readiness")
async def readiness_check(response: Response) -> dict:
    """
    Readiness probe endpoint for Cloud Run.

    Checks if the service is ready to accept traffic by verifying
    that dependencies (Firestore) are reachable. Returns quickly
    to avoid blocking container startup.

    Cloud Run will not send traffic until this endpoint returns 200.

    Args:
        response: FastAPI response object for setting status codes

    Returns:
        dict: Status with ready flag and any issues detected
    """
    issues = []

    # Quick Firestore connectivity check (fail fast)
    try:
        # Try to get Firestore client - this validates configuration
        client = get_firestore_client()
        if client is None:
            issues.append("Firestore client not initialized")
    except Exception as e:
        logger.warning(f"Readiness check: Firestore connectivity issue: {e}")
        issues.append(f"Firestore: {str(e)[:100]}")

    if issues:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "issues": issues}

    return {"status": "ready"}


@router.get("/liveness")
async def liveness_check() -> dict:
    """
    Liveness probe endpoint for Cloud Run.

    Simple endpoint that returns OK to indicate the service is alive
    and not deadlocked. Does not check dependencies - only verifies
    the application process is responsive.

    Cloud Run will restart the container if this endpoint fails repeatedly.

    Returns:
        dict: Status indicating service is alive
    """
    return {"status": "alive"}
