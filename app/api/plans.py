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
"""Plan ingestion API endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Response, status

from app.models.plan import PlanCreateResponse, PlanIn
from app.services.firestore_service import (
    FirestoreOperationError,
    PlanConflictError,
    PlanIngestionOutcome,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=PlanCreateResponse,
    responses={
        201: {
            "description": "Plan created successfully",
            "model": PlanCreateResponse,
        },
        200: {
            "description": "Idempotent ingestion - plan already exists with identical payload",
            "model": PlanCreateResponse,
        },
        400: {
            "description": "Validation error - invalid UUID, empty specs, or malformed payload",
            "content": {
                "application/json": {"example": {"detail": "Invalid UUID string: not-a-uuid"}}
            },
        },
        409: {
            "description": "Conflict - plan exists with different payload",
            "content": {
                "application/json": {
                    "example": {"detail": "Plan already exists with different body"}
                }
            },
        },
        500: {
            "description": "Internal server error",
            "content": {"application/json": {"example": {"detail": "Internal server error"}}},
        },
    },
)
async def create_plan(plan_in: PlanIn, response: Response) -> PlanCreateResponse:
    """
    Create a new plan with specifications.

    This endpoint accepts a plan ingestion request, validates it, and persists
    it to Firestore. It implements idempotent behavior:
    - Returns 201 Created for new plans
    - Returns 200 OK for duplicate ingestions with identical payload
    - Returns 409 Conflict for duplicate plan IDs with different payload

    Validation:
    - Plan ID must be a valid UUID string
    - At least one specification must be provided
    - All required fields must be present

    Args:
        plan_in: Plan ingestion request payload

    Returns:
        PlanCreateResponse with plan_id and status

    Raises:
        HTTPException: 409 for conflicts, 500 for server errors
    """
    # Import here to avoid circular import at module load time
    from app.dependencies import create_plan as create_plan_service

    try:
        # Log ingestion attempt
        logger.info(
            "Plan ingestion request received",
            extra={
                "plan_id": plan_in.id,
                "spec_count": len(plan_in.specs),
            },
        )

        # Call Firestore service to create plan
        outcome, plan_id = create_plan_service(plan_in)

        # Map outcome to HTTP response
        if outcome == PlanIngestionOutcome.CREATED:
            logger.info(
                "Plan created successfully",
                extra={
                    "plan_id": plan_id,
                    "outcome": outcome.value,
                },
            )
            return PlanCreateResponse(plan_id=plan_id, status="running")

        elif outcome == PlanIngestionOutcome.IDENTICAL:
            # Idempotent replay - log explicitly for observability
            logger.info(
                "Idempotent ingestion - plan already exists with identical payload",
                extra={
                    "plan_id": plan_id,
                    "outcome": outcome.value,
                    "idempotent": True,
                },
            )
            # Return 200 OK for idempotent replays
            response.status_code = status.HTTP_200_OK
            return PlanCreateResponse(plan_id=plan_id, status="running")

    except PlanConflictError as e:
        # Plan exists with different body
        error_msg = f"Plan {plan_in.id} already exists with different body"
        logger.warning(
            "Plan ingestion conflict",
            extra={
                "plan_id": plan_in.id,
                "error": error_msg,
                "stored_digest": e.stored_digest,
                "incoming_digest": e.incoming_digest,
            },
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_msg) from e

    except FirestoreOperationError as e:
        # Firestore operation failed
        error_msg = "Internal server error"
        logger.error(
            "Plan ingestion failed due to Firestore error",
            extra={
                "plan_id": plan_in.id,
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
        ) from e

    except Exception as e:
        # Unexpected error
        error_msg = "Internal server error"
        logger.error(
            "Plan ingestion failed due to unexpected error",
            extra={
                "plan_id": getattr(plan_in, "id", "unknown"),
                "error": str(e),
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
        ) from e
