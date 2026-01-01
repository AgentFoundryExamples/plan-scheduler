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
"""Pub/Sub webhook endpoint for spec status updates."""

import logging
import secrets

from fastapi import APIRouter, Header, HTTPException, Response, status
from pydantic import ValidationError

from app.auth import OIDCValidationError, validate_oidc_token
from app.config import get_settings
from app.models.pubsub import PubSubPushEnvelope, SpecStatusPayload, decode_pubsub_message
from app.services.execution_service import ExecutionService
from app.services.firestore_service import (
    FirestoreOperationError,
    get_client,
    process_spec_status_update,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pubsub", tags=["pubsub"])


@router.post(
    "/spec-status",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {
            "description": "Status update processed successfully",
        },
        401: {
            "description": "Unauthorized - invalid authentication",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid or missing authentication"}
                }
            },
        },
        400: {
            "description": "Bad request - invalid payload",
            "content": {"application/json": {"example": {"detail": "Invalid message payload"}}},
        },
        500: {
            "description": "Internal server error",
            "content": {"application/json": {"example": {"detail": "Internal server error"}}},
        },
    },
)
async def spec_status_update(
    envelope: PubSubPushEnvelope,
    response: Response,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_goog_pubsub_verification_token: str | None = Header(
        default=None, alias="x-goog-pubsub-verification-token"
    ),
) -> Response:
    """
    Receive and process Pub/Sub push notifications for spec status updates.

    This endpoint:
    1. Verifies authentication (OIDC JWT or shared token)
    2. Decodes the base64-encoded message payload
    3. Validates the payload against SpecStatusPayload schema
    4. Processes the status update transactionally in Firestore
    5. Triggers execution for the next spec if applicable
    6. Returns 204 No Content quickly

    Security:
    - Primary: OIDC JWT validation when PUBSUB_OIDC_ENABLED is True
      - Validates Authorization header contains valid Google-signed JWT
      - Verifies audience, issuer, and optionally service account email
    - Fallback: Shared token verification when OIDC is disabled or fails
      - Requires PUBSUB_VERIFICATION_TOKEN to be set in environment
      - Verifies token from x-goog-pubsub-verification-token header
    - Returns 401 if neither authentication method succeeds

    Idempotency:
    - Detects duplicate messages via messageId in history
    - Safely handles retries from Pub/Sub

    Args:
        envelope: Pub/Sub push envelope containing message and metadata
        response: FastAPI response object
        authorization: Authorization header for OIDC JWT authentication
        x_goog_pubsub_verification_token: Verification token from Pub/Sub header

    Returns:
        Response with 204 No Content

    Raises:
        HTTPException: 401 for auth failures, 400 for invalid payloads, 500 for server errors
    """
    settings = get_settings()

    # Step 1: Verify authentication (OIDC or shared token)
    auth_method = None
    auth_failure_reason = None

    # Try OIDC authentication first if enabled
    if settings.PUBSUB_OIDC_ENABLED and settings.PUBSUB_EXPECTED_AUDIENCE:
        if authorization:
            try:
                # Extract token from Authorization header
                # Expected format: "Bearer <token>"
                if not authorization.startswith("Bearer "):
                    logger.warning(
                        "Malformed Authorization header: missing 'Bearer ' prefix",
                        extra={
                            "message_id": envelope.message.messageId,
                            "auth_header_prefix": authorization[:20] if authorization else None,
                        },
                    )
                    auth_failure_reason = "Malformed Authorization header"
                else:
                    # Extract token using split for robustness
                    parts = authorization.split(" ", 1)
                    if len(parts) == 2:
                        token = parts[1]
                    else:
                        logger.warning(
                            "Malformed Authorization header: empty token",
                            extra={"message_id": envelope.message.messageId},
                        )
                        auth_failure_reason = "Malformed Authorization header"
                        token = None

                    if token:
                        # Validate the OIDC token
                        validate_oidc_token(
                            token=token,
                            expected_audience=settings.PUBSUB_EXPECTED_AUDIENCE,
                            expected_issuer=settings.PUBSUB_EXPECTED_ISSUER,
                            expected_service_account_email=settings.PUBSUB_SERVICE_ACCOUNT_EMAIL
                            or None,
                        )
                        auth_method = "oidc"
                        logger.info(
                            "Pub/Sub request authenticated via OIDC",
                            extra={
                                "message_id": envelope.message.messageId,
                                "auth_method": "oidc",
                                "audience": settings.PUBSUB_EXPECTED_AUDIENCE,
                            },
                        )
            except OIDCValidationError as e:
                logger.warning(
                    f"OIDC validation failed: {str(e)}",
                    extra={
                        "message_id": envelope.message.messageId,
                        "error": str(e),
                    },
                )
                auth_failure_reason = f"OIDC validation failed: {str(e)}"
            except Exception as e:
                logger.error(
                    f"Unexpected error during OIDC validation: {str(e)}",
                    extra={
                        "message_id": envelope.message.messageId,
                        "error": str(e),
                    },
                    exc_info=True,
                )
                auth_failure_reason = "OIDC validation error"
        else:
            logger.debug(
                "Authorization header not provided, OIDC validation skipped",
                extra={"message_id": envelope.message.messageId},
            )
            auth_failure_reason = "Missing Authorization header"

    # Fall back to shared token verification if OIDC failed or is disabled
    if auth_method is None and settings.PUBSUB_VERIFICATION_TOKEN:
        if x_goog_pubsub_verification_token and secrets.compare_digest(
            x_goog_pubsub_verification_token, settings.PUBSUB_VERIFICATION_TOKEN
        ):
            auth_method = "shared_token"
            logger.info(
                "Pub/Sub request authenticated via shared token",
                extra={
                    "message_id": envelope.message.messageId,
                    "auth_method": "shared_token",
                    "oidc_attempted": settings.PUBSUB_OIDC_ENABLED,
                    "oidc_failure_reason": auth_failure_reason,
                },
            )
        else:
            # Determine log level based on whether this was the primary auth method
            if not settings.PUBSUB_OIDC_ENABLED:
                # Shared token was the primary method, log as warning
                log_level = logging.WARNING
            else:
                # OIDC was primary and failed, this is just fallback failure - log as debug
                log_level = logging.DEBUG

            logger.log(
                log_level,
                "Shared token validation failed",
                extra={
                    "message_id": envelope.message.messageId,
                    "oidc_enabled": settings.PUBSUB_OIDC_ENABLED,
                    "oidc_failure_reason": auth_failure_reason,
                    "shared_token_provided": bool(x_goog_pubsub_verification_token),
                },
            )

    # Reject if neither authentication method succeeded
    if auth_method is None:
        failure_details = []
        if settings.PUBSUB_OIDC_ENABLED:
            failure_details.append(f"OIDC: {auth_failure_reason or 'not attempted'}")
        if settings.PUBSUB_VERIFICATION_TOKEN:
            if not x_goog_pubsub_verification_token:
                failure_details.append("Shared token: missing")
            else:
                failure_details.append("Shared token: invalid")

        logger.error(
            "Authentication failed: all methods rejected",
            extra={
                "message_id": envelope.message.messageId,
                "failure_details": "; ".join(failure_details),
                "oidc_enabled": settings.PUBSUB_OIDC_ENABLED,
                "has_shared_token": bool(settings.PUBSUB_VERIFICATION_TOKEN),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication",
        )

    # Step 2: Log full envelope at debug level
    logger.debug(
        "Received Pub/Sub push envelope",
        extra={
            "envelope": envelope.model_dump(),
            "message_id": envelope.message.messageId,
            "subscription": envelope.subscription,
            "publish_time": envelope.message.publishTime,
        },
    )

    # Step 3: Decode and validate message data
    try:
        payload_dict = decode_pubsub_message(envelope.message.data)
        payload = SpecStatusPayload(**payload_dict)
    except ValueError as e:
        logger.error(
            f"Failed to decode Pub/Sub message: {str(e)}",
            extra={"message_id": envelope.message.messageId, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid message payload"
        ) from e
    except ValidationError as e:
        logger.error(
            f"Failed to validate Pub/Sub payload: {str(e)}",
            extra={
                "message_id": envelope.message.messageId,
                "error": str(e),
                "payload": payload_dict,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid message payload"
        ) from e

    # Step 4: Log status transition at info level
    logger.info(
        f"Processing status update: plan_id={payload.plan_id}, "
        f"spec_index={payload.spec_index}, status={payload.status}",
        extra={
            "plan_id": payload.plan_id,
            "spec_index": payload.spec_index,
            "status": payload.status,
            "stage": payload.stage,
            "message_id": envelope.message.messageId,
        },
    )

    # Step 5: Process status update transactionally
    try:
        client = get_client()
        result = process_spec_status_update(
            plan_id=payload.plan_id,
            spec_index=payload.spec_index,
            status=payload.status,
            stage=payload.stage,
            message_id=envelope.message.messageId,
            raw_payload_snippet=payload.model_dump(),
            details=payload.details,
            correlation_id=payload.correlation_id,
            timestamp=payload.timestamp,
            client=client,
        )

        # Log result
        if result["success"]:
            logger.info(
                f"Status update processed: {result['message']}",
                extra={
                    "plan_id": payload.plan_id,
                    "spec_index": payload.spec_index,
                    "action": result["action"],
                    "message_id": envelope.message.messageId,
                },
            )
        else:
            logger.warning(
                f"Status update not applied: {result['message']}",
                extra={
                    "plan_id": payload.plan_id,
                    "spec_index": payload.spec_index,
                    "action": result["action"],
                    "message_id": envelope.message.messageId,
                },
            )

        # Step 6: Trigger execution for next spec if needed (outside transaction)
        if result.get("next_spec_triggered"):
            next_spec_index = payload.spec_index + 1
            try:
                # Fetch next spec data to pass to execution service
                spec_ref = (
                    client.collection("plans")
                    .document(payload.plan_id)
                    .collection("specs")
                    .document(str(next_spec_index))
                )
                spec_snapshot = spec_ref.get()

                if spec_snapshot.exists:
                    from app.models.plan import SpecRecord

                    spec_data = SpecRecord(**spec_snapshot.to_dict())

                    # Trigger execution
                    execution_service = ExecutionService()
                    execution_service.trigger_spec_execution(
                        plan_id=payload.plan_id,
                        spec_index=next_spec_index,
                        spec_data=spec_data,
                    )
                    logger.info(
                        f"Triggered execution for next spec {next_spec_index}",
                        extra={
                            "plan_id": payload.plan_id,
                            "spec_index": next_spec_index,
                        },
                    )
                else:
                    logger.error(
                        f"Next spec {next_spec_index} not found after unblocking",
                        extra={
                            "plan_id": payload.plan_id,
                            "spec_index": next_spec_index,
                        },
                    )
            except Exception as e:
                # Log execution trigger failure but don't fail the request
                # The transaction has already committed successfully
                logger.error(
                    f"Failed to trigger execution for spec {next_spec_index}: {str(e)}",
                    extra={
                        "plan_id": payload.plan_id,
                        "spec_index": next_spec_index,
                        "error": str(e),
                    },
                    exc_info=True,
                )

    except FirestoreOperationError as e:
        logger.error(
            f"Firestore error processing status update: {str(e)}",
            extra={
                "plan_id": payload.plan_id,
                "spec_index": payload.spec_index,
                "error": str(e),
                "message_id": envelope.message.messageId,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
        ) from e
    except Exception as e:
        logger.error(
            f"Unexpected error processing status update: {str(e)}",
            extra={
                "plan_id": payload.plan_id,
                "spec_index": payload.spec_index,
                "error": str(e),
                "message_id": envelope.message.messageId,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
        ) from e

    # Return 204 No Content
    return Response(status_code=status.HTTP_204_NO_CONTENT)
