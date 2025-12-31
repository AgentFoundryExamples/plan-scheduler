"""Tests for configuration and edge cases."""

import logging
import os
from unittest.mock import patch

import pytest

from app.config import Settings, get_settings


def test_settings_default_values():
    """Test that settings have proper default values."""
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings()
        
        assert settings.FIRESTORE_PROJECT_ID == ""
        assert settings.GOOGLE_APPLICATION_CREDENTIALS == ""
        assert settings.PORT == 8080
        assert settings.SERVICE_NAME == "plan-scheduler"
        assert settings.PUBSUB_VERIFICATION_TOKEN == ""


def test_settings_from_environment():
    """Test that settings load from environment variables."""
    test_env = {
        "FIRESTORE_PROJECT_ID": "test-project",
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/creds.json",
        "PORT": "9090",
        "SERVICE_NAME": "test-service",
        "PUBSUB_VERIFICATION_TOKEN": "test-token"
    }
    
    with patch.dict(os.environ, test_env, clear=True):
        settings = Settings()
        
        assert settings.FIRESTORE_PROJECT_ID == "test-project"
        assert settings.GOOGLE_APPLICATION_CREDENTIALS == "/path/to/creds.json"
        assert settings.PORT == 9090
        assert settings.SERVICE_NAME == "test-service"
        assert settings.PUBSUB_VERIFICATION_TOKEN == "test-token"


def test_port_validation_rejects_non_integer():
    """Test that PORT validation rejects non-integer values."""
    with patch.dict(os.environ, {"PORT": "not-a-number"}, clear=True):
        with pytest.raises(ValueError, match="PORT must be a valid integer"):
            Settings()


def test_port_validation_rejects_out_of_range_low():
    """Test that PORT validation rejects values below valid range."""
    with patch.dict(os.environ, {"PORT": "0"}, clear=True):
        with pytest.raises(ValueError, match="PORT must be between 1 and 65535"):
            Settings()


def test_port_validation_rejects_out_of_range_high():
    """Test that PORT validation rejects values above valid range."""
    with patch.dict(os.environ, {"PORT": "65536"}, clear=True):
        with pytest.raises(ValueError, match="PORT must be between 1 and 65535"):
            Settings()


def test_port_accepts_cloud_run_range():
    """Test that PORT accepts values in Cloud Run typical range."""
    valid_ports = [8080, 8081, 8082, 8000, 3000, 5000]
    
    for port in valid_ports:
        with patch.dict(os.environ, {"PORT": str(port)}, clear=True):
            settings = Settings()
            assert settings.PORT == port


def test_missing_env_vars_emit_warnings(caplog):
    """Test that missing critical environment variables emit warnings."""
    with patch.dict(os.environ, {}, clear=True):
        with caplog.at_level(logging.WARNING):
            settings = Settings()
            
            # Check warnings are logged
            warning_messages = [record.message for record in caplog.records if record.levelname == "WARNING"]
            
            assert any("FIRESTORE_PROJECT_ID" in msg for msg in warning_messages)
            assert any("GOOGLE_APPLICATION_CREDENTIALS" in msg for msg in warning_messages)
            assert any("PUBSUB_VERIFICATION_TOKEN" in msg for msg in warning_messages)


def test_settings_singleton_returns_instance():
    """Test that get_settings returns a Settings instance."""
    settings = get_settings()
    assert isinstance(settings, Settings)


def test_port_validation_handles_none():
    """Test that PORT validation handles None value."""
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings()
        assert settings.PORT == 8080


def test_settings_case_sensitive():
    """Test that settings are case sensitive."""
    with patch.dict(os.environ, {
        "port": "9090",  # lowercase should not be picked up
        "PORT": "8888"   # uppercase should be used
    }, clear=True):
        settings = Settings()
        assert settings.PORT == 8888


def test_settings_ignores_extra_env_vars():
    """Test that extra environment variables are ignored."""
    with patch.dict(os.environ, {
        "PORT": "8080",
        "EXTRA_VAR": "should-be-ignored"
    }, clear=True):
        # Should not raise an error
        settings = Settings()
        assert settings.PORT == 8080
        assert not hasattr(settings, "EXTRA_VAR")
