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
"""Tests for OIDC authentication utilities."""

import time
from unittest.mock import patch

import pytest
from google.auth.exceptions import InvalidValue

from app.auth import OIDCValidationError, validate_oidc_token


class TestValidateOIDCToken:
    """Tests for validate_oidc_token function."""

    def test_empty_token_raises_error(self):
        """Test that empty token raises OIDCValidationError."""
        with pytest.raises(OIDCValidationError, match="Token is empty or missing"):
            validate_oidc_token(
                token="",
                expected_audience="https://example.com",
            )

    def test_missing_audience_claim_raises_error(self):
        """Test that token missing audience claim raises OIDCValidationError."""
        # Mock jwt.decode to return token without aud claim
        mock_decoded = {"iss": "https://accounts.google.com", "sub": "test@example.com"}

        with patch("app.auth.jwt.decode", return_value=mock_decoded):
            with pytest.raises(OIDCValidationError, match="missing audience claim"):
                validate_oidc_token(
                    token="fake-token",
                    expected_audience="https://example.com",
                )

    def test_audience_mismatch_raises_error(self):
        """Test that mismatched audience raises OIDCValidationError."""
        mock_decoded = {
            "aud": "https://wrong-audience.com",
            "iss": "https://accounts.google.com",
            "sub": "test@example.com",
        }

        with patch("app.auth.jwt.decode", return_value=mock_decoded):
            with pytest.raises(OIDCValidationError, match="Audience mismatch"):
                validate_oidc_token(
                    token="fake-token",
                    expected_audience="https://example.com",
                )

    def test_missing_issuer_claim_raises_error(self):
        """Test that token missing issuer claim raises OIDCValidationError."""
        mock_decoded = {"aud": "https://example.com", "sub": "test@example.com"}

        with patch("app.auth.jwt.decode", return_value=mock_decoded):
            with pytest.raises(OIDCValidationError, match="missing issuer claim"):
                validate_oidc_token(
                    token="fake-token",
                    expected_audience="https://example.com",
                )

    def test_issuer_mismatch_raises_error(self):
        """Test that mismatched issuer raises OIDCValidationError."""
        mock_decoded = {
            "aud": "https://example.com",
            "iss": "https://evil.com",
            "sub": "test@example.com",
        }

        with patch("app.auth.jwt.decode", return_value=mock_decoded):
            with pytest.raises(OIDCValidationError, match="Issuer mismatch"):
                validate_oidc_token(
                    token="fake-token",
                    expected_audience="https://example.com",
                    expected_issuer="https://accounts.google.com",
                )

    def test_service_account_mismatch_raises_error(self):
        """Test that mismatched service account email raises OIDCValidationError."""
        mock_decoded = {
            "aud": "https://example.com",
            "iss": "https://accounts.google.com",
            "sub": "wrong@example.com",
            "email": "wrong@example.com",
        }

        with patch("app.auth.jwt.decode", return_value=mock_decoded):
            with pytest.raises(OIDCValidationError, match="Service account mismatch"):
                validate_oidc_token(
                    token="fake-token",
                    expected_audience="https://example.com",
                    expected_service_account_email="correct@example.com",
                )

    def test_valid_token_succeeds(self):
        """Test that valid token with correct claims succeeds."""
        mock_decoded = {
            "aud": "https://example.com",
            "iss": "https://accounts.google.com",
            "sub": "test@example.com",
            "email": "test@example.com",
            "exp": int(time.time()) + 3600,
        }

        with patch("app.auth.jwt.decode", return_value=mock_decoded):
            result = validate_oidc_token(
                token="fake-token",
                expected_audience="https://example.com",
            )

            assert result == mock_decoded

    def test_valid_token_with_service_account_check_succeeds(self):
        """Test that valid token with matching service account succeeds."""
        mock_decoded = {
            "aud": "https://example.com",
            "iss": "https://accounts.google.com",
            "sub": "test@example.com",
            "email": "test@example.com",
        }

        with patch("app.auth.jwt.decode", return_value=mock_decoded):
            result = validate_oidc_token(
                token="fake-token",
                expected_audience="https://example.com",
                expected_service_account_email="test@example.com",
            )

            assert result == mock_decoded

    def test_google_auth_error_raises_oidc_validation_error(self):
        """Test that GoogleAuthError is wrapped in OIDCValidationError."""
        with patch("app.auth.jwt.decode", side_effect=InvalidValue("Expired token")):
            with pytest.raises(OIDCValidationError, match="Token verification failed"):
                validate_oidc_token(
                    token="fake-token",
                    expected_audience="https://example.com",
                )

    def test_unexpected_error_raises_oidc_validation_error(self):
        """Test that unexpected errors are wrapped in OIDCValidationError."""
        with patch("app.auth.jwt.decode", side_effect=ValueError("Unexpected error")):
            with pytest.raises(OIDCValidationError, match="Unexpected validation error"):
                validate_oidc_token(
                    token="fake-token",
                    expected_audience="https://example.com",
                )

    def test_none_service_account_skips_validation(self):
        """Test that None service account email skips validation."""
        mock_decoded = {
            "aud": "https://example.com",
            "iss": "https://accounts.google.com",
            "sub": "test@example.com",
            "email": "any@example.com",
        }

        with patch("app.auth.jwt.decode", return_value=mock_decoded):
            result = validate_oidc_token(
                token="fake-token",
                expected_audience="https://example.com",
                expected_service_account_email=None,
            )

            assert result == mock_decoded

    def test_service_account_matches_email_field(self):
        """Test that service account can match email field instead of sub."""
        mock_decoded = {
            "aud": "https://example.com",
            "iss": "https://accounts.google.com",
            "sub": "different@example.com",
            "email": "test@example.com",
            "email_verified": True,  # Email is verified
        }

        with patch("app.auth.jwt.decode", return_value=mock_decoded):
            result = validate_oidc_token(
                token="fake-token",
                expected_audience="https://example.com",
                expected_service_account_email="test@example.com",
            )

            assert result == mock_decoded

    def test_service_account_email_not_verified_raises_error(self):
        """Test that unverified email raises OIDCValidationError."""
        mock_decoded = {
            "aud": "https://example.com",
            "iss": "https://accounts.google.com",
            "sub": "different@example.com",
            "email": "test@example.com",
            "email_verified": False,  # Email is NOT verified
        }

        with patch("app.auth.jwt.decode", return_value=mock_decoded):
            with pytest.raises(OIDCValidationError, match="Service account email is not verified"):
                validate_oidc_token(
                    token="fake-token",
                    expected_audience="https://example.com",
                    expected_service_account_email="test@example.com",
                )
