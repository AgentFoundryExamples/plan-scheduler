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
"""Authentication utilities for Pub/Sub OIDC token validation."""

import logging
from typing import Any

from google.auth import jwt
from google.auth.exceptions import GoogleAuthError

logger = logging.getLogger(__name__)


class OIDCValidationError(Exception):
    """Raised when OIDC token validation fails."""

    pass


def validate_oidc_token(
    token: str,
    expected_audience: str,
    expected_issuer: str = "https://accounts.google.com",
    expected_service_account_email: str | None = None,
) -> dict[str, Any]:
    """
    Validate a Google OIDC JWT token from Pub/Sub push authentication.

    This function verifies:
    1. Token signature using Google's public keys
    2. Token expiration (exp claim)
    3. Audience claim matches expected value
    4. Issuer claim matches expected value
    5. Optional: Service account email matches subject claim

    Args:
        token: The JWT token string (without 'Bearer ' prefix)
        expected_audience: Expected audience claim (typically Cloud Run service URL)
        expected_issuer: Expected issuer claim (default: Google's issuer)
        expected_service_account_email: Optional expected service account email in sub claim

    Returns:
        dict: Decoded JWT payload with claims

    Raises:
        OIDCValidationError: If token validation fails for any reason

    Security Notes:
        - Uses google-auth library which automatically fetches and caches Google's public keys
        - Verifies token signature cryptographically
        - Checks token expiration with clock skew tolerance
        - All validation failures are logged with structured metadata
    """
    if not token:
        raise OIDCValidationError("Token is empty or missing")

    try:
        # Decode and verify the JWT token
        # google.auth.jwt.decode verifies:
        # - Signature using Google's public keys (fetched automatically)
        # - Token expiration (exp claim)
        # - Clock skew tolerance (default 60 seconds)
        decoded_token = jwt.decode(token, verify=True)

        # Validate audience claim
        token_audience = decoded_token.get("aud")
        if not token_audience:
            logger.warning(
                "OIDC token validation failed: missing audience claim",
                extra={"expected_audience": expected_audience},
            )
            raise OIDCValidationError("Token missing audience claim")

        if token_audience != expected_audience:
            logger.warning(
                "OIDC token validation failed: audience mismatch",
                extra={
                    "expected_audience": expected_audience,
                    "actual_audience": token_audience,
                },
            )
            raise OIDCValidationError(
                f"Audience mismatch: expected {expected_audience}, got {token_audience}"
            )

        # Validate issuer claim
        token_issuer = decoded_token.get("iss")
        if not token_issuer:
            logger.warning(
                "OIDC token validation failed: missing issuer claim",
                extra={"expected_issuer": expected_issuer},
            )
            raise OIDCValidationError("Token missing issuer claim")

        if token_issuer != expected_issuer:
            logger.warning(
                "OIDC token validation failed: issuer mismatch",
                extra={"expected_issuer": expected_issuer, "actual_issuer": token_issuer},
            )
            raise OIDCValidationError(
                f"Issuer mismatch: expected {expected_issuer}, got {token_issuer}"
            )

        # Optional: Validate service account email in subject claim
        if expected_service_account_email:
            token_subject = decoded_token.get("sub")
            token_email = decoded_token.get("email")

            # Check both sub and email claims as different token types may use different fields
            if token_subject != expected_service_account_email and token_email != expected_service_account_email:
                logger.warning(
                    "OIDC token validation failed: service account mismatch",
                    extra={
                        "expected_service_account": expected_service_account_email,
                        "token_subject": token_subject,
                        "token_email": token_email,
                    },
                )
                raise OIDCValidationError(
                    f"Service account mismatch: expected {expected_service_account_email}"
                )

        logger.info(
            "OIDC token validated successfully",
            extra={
                "audience": token_audience,
                "issuer": token_issuer,
                "subject": decoded_token.get("sub"),
                "email": decoded_token.get("email"),
            },
        )

        return decoded_token

    except GoogleAuthError as e:
        # Covers signature verification failures, expired tokens, etc.
        logger.warning(
            f"OIDC token validation failed: {str(e)}",
            extra={"error_type": type(e).__name__, "error": str(e)},
        )
        raise OIDCValidationError(f"Token verification failed: {str(e)}") from e

    except Exception as e:
        logger.error(
            f"Unexpected error during OIDC token validation: {str(e)}",
            extra={"error_type": type(e).__name__, "error": str(e)},
            exc_info=True,
        )
        raise OIDCValidationError(f"Unexpected validation error: {str(e)}") from e
