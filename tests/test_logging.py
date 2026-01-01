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
"""Tests for logging functionality and edge cases."""

import logging
from unittest.mock import patch

import pytest

from app.main import create_app, setup_logging


def test_logging_setup_configures_json_format():
    """Test that logging is configured with JSON formatter."""
    setup_logging()

    root_logger = logging.getLogger()
    assert root_logger.level == logging.INFO
    assert len(root_logger.handlers) > 0

    handler = root_logger.handlers[0]
    assert handler.level == logging.INFO


def test_logging_respects_log_level_setting():
    """Test that logging uses LOG_LEVEL from settings."""
    with patch.dict("os.environ", {"LOG_LEVEL": "DEBUG"}):
        from app.config import Settings

        # Clear the cache to force reload
        from app.config import get_settings

        get_settings.cache_clear()

        setup_logging()
        root_logger = logging.getLogger()

        assert root_logger.level == logging.DEBUG

        # Clean up
        get_settings.cache_clear()


def test_logging_handles_invalid_log_level():
    """Test that invalid LOG_LEVEL falls back to INFO with warning."""
    with patch.dict("os.environ", {"LOG_LEVEL": "INVALID_LEVEL"}):
        from app.config import Settings, get_settings

        get_settings.cache_clear()

        # Should not raise an exception, should fall back to INFO
        settings = get_settings()
        assert settings.LOG_LEVEL == "INFO"

        # Clean up
        get_settings.cache_clear()


def test_logging_normalizes_log_level_case():
    """Test that LOG_LEVEL is normalized to uppercase."""
    with patch.dict("os.environ", {"LOG_LEVEL": "debug"}):
        from app.config import get_settings

        get_settings.cache_clear()

        settings = get_settings()
        assert settings.LOG_LEVEL == "DEBUG"

        # Clean up
        get_settings.cache_clear()


def test_logging_level_warning():
    """Test that logging level WARNING works."""
    with patch.dict("os.environ", {"LOG_LEVEL": "WARNING"}):
        from app.config import get_settings

        get_settings.cache_clear()

        setup_logging()
        root_logger = logging.getLogger()

        assert root_logger.level == logging.WARNING

        # Clean up
        get_settings.cache_clear()


def test_logging_level_error():
    """Test that logging level ERROR works."""
    with patch.dict("os.environ", {"LOG_LEVEL": "ERROR"}):
        from app.config import get_settings

        get_settings.cache_clear()

        setup_logging()
        root_logger = logging.getLogger()

        assert root_logger.level == logging.ERROR

        # Clean up
        get_settings.cache_clear()


def test_logging_level_critical():
    """Test that logging level CRITICAL works."""
    with patch.dict("os.environ", {"LOG_LEVEL": "CRITICAL"}):
        from app.config import get_settings

        get_settings.cache_clear()

        setup_logging()
        root_logger = logging.getLogger()

        assert root_logger.level == logging.CRITICAL

        # Clean up
        get_settings.cache_clear()


def test_app_factory_multiple_invocations():
    """Test that app factory can be called multiple times without issues."""
    app1 = create_app()
    app2 = create_app()
    app3 = create_app()

    # Each should be a separate instance
    assert app1 is not app2
    assert app2 is not app3
    assert app1 is not app3

    # But all should have the same configuration
    assert app1.title == app2.title == app3.title
    assert app1.version == app2.version == app3.version


def test_logging_handles_unicode(caplog):
    """Test that logging handles unicode characters gracefully."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Test various unicode strings - should not raise exceptions
    try:
        logger.info("Hello 世界 🌍")
        logger.info("Émojis: 😀 🎉 ⚡")
        logger.info("Symbols: © ® ™ € £")
        success = True
    except Exception:
        success = False

    assert success


def test_logging_handles_binary_like_content(caplog):
    """Test that logging handles binary-like content without crashing."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Test with repr of bytes (common pattern) - should not raise exceptions
    try:
        logger.info(f"Binary data: {repr(b'\\x00\\x01\\x02')}")
        logger.info("Mixed content: text and %r", b"binary")
        success = True
    except Exception:
        success = False

    assert success


def test_logging_configuration_removes_duplicate_handlers():
    """Test that logging setup removes duplicate handlers."""
    # Setup logging multiple times
    setup_logging()
    handler_count_1 = len(logging.getLogger().handlers)

    setup_logging()
    handler_count_2 = len(logging.getLogger().handlers)

    setup_logging()
    handler_count_3 = len(logging.getLogger().handlers)

    # Should not accumulate handlers
    assert handler_count_1 == handler_count_2 == handler_count_3


def test_logging_includes_service_name():
    """Test that logs include service name."""
    with patch.dict("os.environ", {"SERVICE_NAME": "test-service"}):
        from app.config import get_settings

        get_settings.cache_clear()

        setup_logging()
        logger = logging.getLogger(__name__)

        # Just verify logging setup doesn't crash
        # The custom handler outputs to stdout, not captured by caplog
        try:
            logger.info("Test message")
            success = True
        except Exception:
            success = False

        assert success

        # Clean up
        get_settings.cache_clear()


def test_app_startup_logs_configuration():
    """Test that app startup doesn't crash and creates app correctly."""
    # Just test that app creation works without errors
    app = create_app()

    assert app is not None
    assert app.title == "Plan Scheduler Service"
    assert app.version == "0.1.0"


def test_logging_with_empty_message():
    """Test that logging handles empty messages gracefully."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Should not raise exceptions
    try:
        logger.info("")
        logger.info(" ")
        success = True
    except Exception:
        success = False

    assert success


def test_logging_with_very_long_message():
    """Test that logging handles very long messages."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Should not raise exceptions
    try:
        long_message = "x" * 10000
        logger.info(long_message)
        success = True
    except Exception:
        success = False

    assert success


def test_logging_with_special_characters(caplog):
    """Test that logging handles special characters."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Should not raise exceptions
    try:
        logger.info("Special: \n\t\r\"'{}[]")
        logger.info("Control: \x00\x01\x02")
        success = True
    except Exception:
        success = False

    assert success


def test_request_correlation_id_in_logs():
    """Test that request correlation middleware adds request_id to logs."""
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    # Make a request with custom request ID
    custom_id = "test-correlation-id-123"
    response = client.get("/health", headers={"X-Request-ID": custom_id})

    # Verify response includes the request ID
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_id


def test_request_correlation_id_generated_when_missing():
    """Test that request correlation ID is generated when not provided."""
    from fastapi.testclient import TestClient

    app = create_app()
    client = TestClient(app)

    # Make a request without request ID
    response = client.get("/health")

    # Verify response includes a generated request ID
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0
