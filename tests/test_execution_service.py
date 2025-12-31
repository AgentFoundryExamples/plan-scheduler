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
"""Tests for execution service."""

import logging
import os
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.models.plan import SpecRecord
from app.services.execution_service import ExecutionService


@pytest.fixture
def sample_spec_record() -> SpecRecord:
    """Create a sample SpecRecord for testing."""
    return SpecRecord(
        spec_index=0,
        purpose="Test purpose",
        vision="Test vision",
        must=["requirement1", "requirement2"],
        dont=["avoid1"],
        nice=["nice-to-have1"],
        assumptions=["assumption1"],
        status="running",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, 12, 30, 0, tzinfo=UTC),
        history=[],
    )


@pytest.fixture
def execution_service_factory():
    """Factory fixture to create an ExecutionService with a specific config."""

    def _factory(enabled: bool):
        with patch.dict(os.environ, {"EXECUTION_ENABLED": str(enabled).lower()}):
            from app.config import get_settings

            get_settings.cache_clear()
            service = ExecutionService()
            return service

    yield _factory
    # Final cache clear after all tests using the factory are done
    from app.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def execution_service_enabled(execution_service_factory):
    """Create ExecutionService with EXECUTION_ENABLED=True."""
    return execution_service_factory(enabled=True)


@pytest.fixture
def execution_service_disabled(execution_service_factory):
    """Create ExecutionService with EXECUTION_ENABLED=False."""
    return execution_service_factory(enabled=False)


def test_execution_service_initialization():
    """Test that ExecutionService initializes properly."""
    service = ExecutionService()
    assert service.logger is not None
    assert service.settings is not None


def test_trigger_spec_execution_enabled_logs_info(
    execution_service_enabled, sample_spec_record, caplog
):
    """Test that trigger_spec_execution logs info when enabled."""
    plan_id = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"
    spec_index = 0

    with caplog.at_level(logging.INFO):
        execution_service_enabled.trigger_spec_execution(
            plan_id=plan_id, spec_index=spec_index, spec_data=sample_spec_record
        )

    # Check that info log was created
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelname == "INFO"
    assert "Triggering spec execution" in record.message

    # Check that extra fields are present
    assert record.plan_id == plan_id
    assert record.spec_index == spec_index
    assert record.status == "running"
    assert record.execution_enabled is True

    # Check that spec_data is serialized
    assert hasattr(record, "spec_data")
    spec_data = record.spec_data
    assert spec_data["spec_index"] == 0
    assert spec_data["purpose"] == "Test purpose"
    assert spec_data["vision"] == "Test vision"
    assert spec_data["status"] == "running"


def test_trigger_spec_execution_disabled_logs_skip(
    execution_service_disabled, sample_spec_record, caplog
):
    """Test that trigger_spec_execution logs skip message when disabled."""
    plan_id = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"
    spec_index = 0

    with caplog.at_level(logging.INFO):
        execution_service_disabled.trigger_spec_execution(
            plan_id=plan_id, spec_index=spec_index, spec_data=sample_spec_record
        )

    # Check that skip log was created
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelname == "INFO"
    assert "Execution service disabled" in record.message
    assert "skipping spec execution trigger" in record.message

    # Check that extra fields are present
    assert record.plan_id == plan_id
    assert record.spec_index == spec_index
    assert record.status == "running"
    assert record.execution_enabled is False

    # Spec data should not be in the skip message
    assert not hasattr(record, "spec_data")


def test_trigger_spec_execution_includes_all_required_fields(
    execution_service_enabled, sample_spec_record, caplog
):
    """Test that all required fields are logged."""
    plan_id = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"
    spec_index = 42

    with caplog.at_level(logging.INFO):
        execution_service_enabled.trigger_spec_execution(
            plan_id=plan_id, spec_index=spec_index, spec_data=sample_spec_record
        )

    record = caplog.records[0]

    # Check all required fields are present
    assert record.plan_id == plan_id
    assert record.spec_index == spec_index
    assert record.status == sample_spec_record.status

    # Check spec_data contains all fields
    spec_data = record.spec_data
    assert "spec_index" in spec_data
    assert "purpose" in spec_data
    assert "vision" in spec_data
    assert "must" in spec_data
    assert "dont" in spec_data
    assert "nice" in spec_data
    assert "assumptions" in spec_data
    assert "status" in spec_data
    assert "created_at" in spec_data
    assert "updated_at" in spec_data
    assert "history" in spec_data


def test_serialize_spec_data_converts_datetime_to_iso_string(execution_service_enabled):
    """Test that datetime fields are converted to ISO 8601 strings."""
    spec_record = SpecRecord(
        spec_index=0,
        purpose="Test",
        vision="Test",
        must=[],
        dont=[],
        nice=[],
        assumptions=[],
        status="blocked",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC),
        history=[],
    )

    serialized = execution_service_enabled._serialize_spec_data(spec_record)

    # Check that datetime fields are strings
    assert isinstance(serialized["created_at"], str)
    assert isinstance(serialized["updated_at"], str)

    # Check ISO 8601 format (pydantic uses 'Z' for UTC timezone)
    assert serialized["created_at"] == "2024-01-01T12:00:00Z"
    assert serialized["updated_at"] == "2024-01-01T13:00:00Z"


def test_serialize_spec_data_preserves_other_field_types(execution_service_enabled):
    """Test that non-datetime fields are preserved correctly."""
    spec_record = SpecRecord(
        spec_index=5,
        purpose="Test purpose",
        vision="Test vision",
        must=["req1", "req2"],
        dont=["avoid1"],
        nice=["nice1"],
        assumptions=["assumption1"],
        status="running",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        history=[{"timestamp": "2024-01-01T12:00:00", "event": "created"}],
    )

    serialized = execution_service_enabled._serialize_spec_data(spec_record)

    # Check that other fields are preserved
    assert serialized["spec_index"] == 5
    assert serialized["purpose"] == "Test purpose"
    assert serialized["vision"] == "Test vision"
    assert serialized["must"] == ["req1", "req2"]
    assert serialized["dont"] == ["avoid1"]
    assert serialized["nice"] == ["nice1"]
    assert serialized["assumptions"] == ["assumption1"]
    assert serialized["status"] == "running"
    assert serialized["history"] == [{"timestamp": "2024-01-01T12:00:00", "event": "created"}]


def test_trigger_spec_execution_with_blocked_status(execution_service_enabled, caplog):
    """Test trigger_spec_execution with blocked status."""
    spec_record = SpecRecord(
        spec_index=1,
        purpose="Test",
        vision="Test",
        must=[],
        dont=[],
        nice=[],
        assumptions=[],
        status="blocked",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        history=[],
    )

    plan_id = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"

    with caplog.at_level(logging.INFO):
        execution_service_enabled.trigger_spec_execution(
            plan_id=plan_id, spec_index=1, spec_data=spec_record
        )

    record = caplog.records[0]
    assert record.status == "blocked"


def test_trigger_spec_execution_with_failed_status(execution_service_enabled, caplog):
    """Test trigger_spec_execution with failed status."""
    spec_record = SpecRecord(
        spec_index=2,
        purpose="Test",
        vision="Test",
        must=[],
        dont=[],
        nice=[],
        assumptions=[],
        status="failed",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        history=[],
    )

    plan_id = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"

    with caplog.at_level(logging.INFO):
        execution_service_enabled.trigger_spec_execution(
            plan_id=plan_id, spec_index=2, spec_data=spec_record
        )

    record = caplog.records[0]
    assert record.status == "failed"


def test_trigger_spec_execution_with_finished_status(execution_service_enabled, caplog):
    """Test trigger_spec_execution with finished status."""
    spec_record = SpecRecord(
        spec_index=3,
        purpose="Test",
        vision="Test",
        must=[],
        dont=[],
        nice=[],
        assumptions=[],
        status="finished",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        history=[],
    )

    plan_id = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"

    with caplog.at_level(logging.INFO):
        execution_service_enabled.trigger_spec_execution(
            plan_id=plan_id, spec_index=3, spec_data=spec_record
        )

    record = caplog.records[0]
    assert record.status == "finished"


def test_trigger_spec_execution_with_empty_lists(execution_service_enabled, caplog):
    """Test trigger_spec_execution with empty list fields."""
    spec_record = SpecRecord(
        spec_index=0,
        purpose="Test purpose",
        vision="Test vision",
        must=[],  # Empty list
        dont=[],  # Empty list
        nice=[],  # Empty list
        assumptions=[],  # Empty list
        status="running",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        history=[],  # Empty history
    )

    plan_id = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"

    with caplog.at_level(logging.INFO):
        execution_service_enabled.trigger_spec_execution(
            plan_id=plan_id, spec_index=0, spec_data=spec_record
        )

    # Should not raise any errors
    record = caplog.records[0]
    spec_data = record.spec_data
    assert spec_data["must"] == []
    assert spec_data["dont"] == []
    assert spec_data["nice"] == []
    assert spec_data["assumptions"] == []
    assert spec_data["history"] == []


def test_execution_service_with_default_config():
    """Test ExecutionService with default configuration (enabled)."""
    with patch.dict(os.environ, {}, clear=False):
        from app.config import get_settings

        get_settings.cache_clear()
        service = ExecutionService()

        # Default should be enabled
        assert service.settings.EXECUTION_ENABLED is True

        get_settings.cache_clear()


def test_execution_service_returns_none_when_enabled(execution_service_enabled, sample_spec_record):
    """Test that trigger_spec_execution returns None when enabled."""
    result = execution_service_enabled.trigger_spec_execution(
        plan_id="test-id", spec_index=0, spec_data=sample_spec_record
    )
    assert result is None


def test_execution_service_returns_none_when_disabled(
    execution_service_disabled, sample_spec_record
):
    """Test that trigger_spec_execution returns None when disabled."""
    result = execution_service_disabled.trigger_spec_execution(
        plan_id="test-id", spec_index=0, spec_data=sample_spec_record
    )
    assert result is None


def test_serialize_spec_data_handles_complex_history(execution_service_enabled):
    """Test that complex history data is serialized correctly."""
    spec_record = SpecRecord(
        spec_index=0,
        purpose="Test",
        vision="Test",
        must=[],
        dont=[],
        nice=[],
        assumptions=[],
        status="running",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        history=[
            {"event": "created", "timestamp": "2024-01-01T12:00:00"},
            {"event": "updated", "timestamp": "2024-01-01T13:00:00", "field": "status"},
            {
                "event": "state_change",
                "timestamp": "2024-01-01T14:00:00",
                "from": "blocked",
                "to": "running",
            },
        ],
    )

    serialized = execution_service_enabled._serialize_spec_data(spec_record)

    # Check history is preserved
    assert len(serialized["history"]) == 3
    assert serialized["history"][0]["event"] == "created"
    assert serialized["history"][1]["field"] == "status"
    assert serialized["history"][2]["from"] == "blocked"


def test_trigger_spec_execution_with_special_characters_in_fields(
    execution_service_enabled, caplog
):
    """Test that special characters in fields are handled correctly."""
    spec_record = SpecRecord(
        spec_index=0,
        purpose='Test "purpose" with quotes',
        vision="Test vision with\nnewlines",
        must=["req with 'single quotes'"],
        dont=["avoid & symbols"],
        nice=["nice <tag>"],
        assumptions=["assumption with \t tabs"],
        status="running",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        history=[],
    )

    plan_id = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"

    with caplog.at_level(logging.INFO):
        execution_service_enabled.trigger_spec_execution(
            plan_id=plan_id, spec_index=0, spec_data=spec_record
        )

    # Should not raise any errors
    record = caplog.records[0]
    spec_data = record.spec_data
    assert 'Test "purpose" with quotes' in spec_data["purpose"]
    assert "Test vision with\nnewlines" in spec_data["vision"]


def test_execution_service_disabled_early_return(
    execution_service_disabled, sample_spec_record, caplog
):
    """Test that disabled service returns early without processing spec_data."""
    plan_id = "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d"

    with caplog.at_level(logging.INFO):
        execution_service_disabled.trigger_spec_execution(
            plan_id=plan_id, spec_index=0, spec_data=sample_spec_record
        )

    # Only one log record (the skip message)
    assert len(caplog.records) == 1
    # No serialization should happen for spec_data
    assert not hasattr(caplog.records[0], "spec_data")
