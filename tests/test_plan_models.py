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
"""Tests for plan ingestion schemas and records."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.plan import (
    PlanCreateResponse,
    PlanIn,
    PlanRecord,
    PlanStatus,
    PlanStatusOut,
    SpecIn,
    SpecRecord,
    SpecStatus,
    SpecStatusOut,
    create_initial_plan_record,
    create_initial_spec_record,
)


class TestSpecIn:
    """Tests for SpecIn model."""

    def test_spec_in_with_all_fields(self):
        """Test SpecIn creation with all fields populated."""
        spec = SpecIn(
            purpose="Test purpose",
            vision="Test vision",
            must=["must1", "must2"],
            dont=["dont1"],
            nice=["nice1", "nice2", "nice3"],
            assumptions=["assumption1"],
        )

        assert spec.purpose == "Test purpose"
        assert spec.vision == "Test vision"
        assert spec.must == ["must1", "must2"]
        assert spec.dont == ["dont1"]
        assert spec.nice == ["nice1", "nice2", "nice3"]
        assert spec.assumptions == ["assumption1"]

    def test_spec_in_with_empty_lists(self):
        """Test SpecIn allows empty lists for all list fields."""
        spec = SpecIn(
            purpose="Test purpose",
            vision="Test vision",
            must=[],
            dont=[],
            nice=[],
            assumptions=[],
        )

        assert spec.must == []
        assert spec.dont == []
        assert spec.nice == []
        assert spec.assumptions == []

    def test_spec_in_defaults_to_empty_lists(self):
        """Test SpecIn defaults list fields to empty lists when not provided."""
        spec = SpecIn(purpose="Test purpose", vision="Test vision")

        assert spec.must == []
        assert spec.dont == []
        assert spec.nice == []
        assert spec.assumptions == []

    def test_spec_in_converts_none_to_empty_list(self):
        """Test SpecIn converts None values to empty lists via validator."""
        # Using model_validate to bypass pydantic's default validation
        spec = SpecIn.model_validate(
            {
                "purpose": "Test purpose",
                "vision": "Test vision",
                "must": None,
                "dont": None,
                "nice": None,
                "assumptions": None,
            }
        )

        assert spec.must == []
        assert spec.dont == []
        assert spec.nice == []
        assert spec.assumptions == []

    def test_spec_in_requires_purpose(self):
        """Test SpecIn raises error when purpose is missing."""
        with pytest.raises(ValidationError) as exc_info:
            SpecIn(vision="Test vision")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("purpose",) for e in errors)

    def test_spec_in_requires_vision(self):
        """Test SpecIn raises error when vision is missing."""
        with pytest.raises(ValidationError) as exc_info:
            SpecIn(purpose="Test purpose")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("vision",) for e in errors)

    def test_spec_in_serialization(self):
        """Test SpecIn serializes correctly to dict."""
        spec = SpecIn(
            purpose="Test purpose",
            vision="Test vision",
            must=["must1"],
            dont=[],
            nice=["nice1", "nice2"],
            assumptions=[],
        )

        data = spec.model_dump()
        assert data["purpose"] == "Test purpose"
        assert data["vision"] == "Test vision"
        assert data["must"] == ["must1"]
        assert data["dont"] == []
        assert data["nice"] == ["nice1", "nice2"]
        assert data["assumptions"] == []


class TestPlanIn:
    """Tests for PlanIn model."""

    def test_plan_in_with_valid_uuid_and_specs(self):
        """Test PlanIn creation with valid UUID and specs."""
        plan_id = str(uuid4())
        spec1 = SpecIn(purpose="Purpose 1", vision="Vision 1")
        spec2 = SpecIn(purpose="Purpose 2", vision="Vision 2")

        plan = PlanIn(id=plan_id, specs=[spec1, spec2])

        assert plan.id == plan_id
        assert len(plan.specs) == 2
        assert plan.specs[0].purpose == "Purpose 1"
        assert plan.specs[1].purpose == "Purpose 2"

    def test_plan_in_validates_uuid_format(self):
        """Test PlanIn rejects invalid UUID strings."""
        spec = SpecIn(purpose="Test", vision="Test")

        with pytest.raises(ValidationError) as exc_info:
            PlanIn(id="not-a-uuid", specs=[spec])

        errors = exc_info.value.errors()
        assert any("Invalid UUID string" in str(e) for e in errors)

    def test_plan_in_rejects_empty_uuid(self):
        """Test PlanIn rejects empty string as UUID."""
        spec = SpecIn(purpose="Test", vision="Test")

        with pytest.raises(ValidationError) as exc_info:
            PlanIn(id="", specs=[spec])

        errors = exc_info.value.errors()
        assert any("Invalid UUID string" in str(e) for e in errors)

    def test_plan_in_requires_at_least_one_spec(self):
        """Test PlanIn requires at least one specification."""
        plan_id = str(uuid4())

        with pytest.raises(ValidationError) as exc_info:
            PlanIn(id=plan_id, specs=[])

        errors = exc_info.value.errors()
        assert any("At least one specification must be provided" in str(e) for e in errors)

    def test_plan_in_with_multiple_specs(self):
        """Test PlanIn with multiple specifications."""
        plan_id = str(uuid4())
        specs = [
            SpecIn(purpose=f"Purpose {i}", vision=f"Vision {i}", must=[f"must{i}"])
            for i in range(5)
        ]

        plan = PlanIn(id=plan_id, specs=specs)

        assert len(plan.specs) == 5
        for i, spec in enumerate(plan.specs):
            assert spec.purpose == f"Purpose {i}"
            assert spec.vision == f"Vision {i}"
            assert spec.must == [f"must{i}"]

    def test_plan_in_serialization(self):
        """Test PlanIn serializes correctly to dict."""
        plan_id = str(uuid4())
        spec = SpecIn(purpose="Test", vision="Test", must=["item1"])
        plan = PlanIn(id=plan_id, specs=[spec])

        data = plan.model_dump()
        assert data["id"] == plan_id
        assert len(data["specs"]) == 1
        assert data["specs"][0]["purpose"] == "Test"
        assert data["specs"][0]["must"] == ["item1"]


class TestPlanCreateResponse:
    """Tests for PlanCreateResponse model."""

    def test_plan_create_response_with_running_status(self):
        """Test PlanCreateResponse with running status."""
        response = PlanCreateResponse(plan_id=str(uuid4()), status="running")

        assert response.status == "running"

    def test_plan_create_response_with_finished_status(self):
        """Test PlanCreateResponse with finished status."""
        response = PlanCreateResponse(plan_id=str(uuid4()), status="finished")

        assert response.status == "finished"

    def test_plan_create_response_with_failed_status(self):
        """Test PlanCreateResponse with failed status."""
        response = PlanCreateResponse(plan_id=str(uuid4()), status="failed")

        assert response.status == "failed"

    def test_plan_create_response_rejects_invalid_status(self):
        """Test PlanCreateResponse rejects invalid status values."""
        with pytest.raises(ValidationError) as exc_info:
            PlanCreateResponse(plan_id=str(uuid4()), status="blocked")

        errors = exc_info.value.errors()
        assert any("status" in str(e) for e in errors)

    def test_plan_create_response_rejects_empty_status(self):
        """Test PlanCreateResponse rejects empty status."""
        with pytest.raises(ValidationError) as exc_info:
            PlanCreateResponse(plan_id=str(uuid4()), status="")

        errors = exc_info.value.errors()
        assert any("status" in str(e) for e in errors)


class TestSpecRecord:
    """Tests for SpecRecord model."""

    def test_spec_record_creation(self):
        """Test SpecRecord creation with all required fields."""
        now = datetime.now(UTC)
        record = SpecRecord(
            spec_index=0,
            purpose="Test purpose",
            vision="Test vision",
            must=["must1"],
            dont=["dont1"],
            nice=["nice1"],
            assumptions=["assumption1"],
            status="blocked",
            created_at=now,
            updated_at=now,
            history=[],
        )

        assert record.spec_index == 0
        assert record.purpose == "Test purpose"
        assert record.status == "blocked"
        assert record.created_at == now
        assert record.updated_at == now
        assert record.history == []

    def test_spec_record_status_values(self):
        """Test SpecRecord accepts all valid status values."""
        now = datetime.now(UTC)
        valid_statuses = ["blocked", "running", "finished", "failed"]

        for status in valid_statuses:
            record = SpecRecord(
                spec_index=0,
                purpose="Test",
                vision="Test",
                status=status,
                created_at=now,
                updated_at=now,
            )
            assert record.status == status

    def test_spec_record_rejects_invalid_status(self):
        """Test SpecRecord rejects invalid status values."""
        now = datetime.now(UTC)

        with pytest.raises(ValidationError) as exc_info:
            SpecRecord(
                spec_index=0,
                purpose="Test",
                vision="Test",
                status="invalid",
                created_at=now,
                updated_at=now,
            )

        errors = exc_info.value.errors()
        assert any("status" in str(e) for e in errors)

    def test_spec_record_timezone_aware_timestamps(self):
        """Test SpecRecord ensures timestamps are timezone-aware."""
        naive_dt = datetime(2025, 1, 1, 12, 0, 0)
        record = SpecRecord.model_validate(
            {
                "spec_index": 0,
                "purpose": "Test",
                "vision": "Test",
                "status": "blocked",
                "created_at": naive_dt,
                "updated_at": naive_dt,
            }
        )

        assert record.created_at.tzinfo == UTC
        assert record.updated_at.tzinfo == UTC

    def test_spec_record_defaults_empty_lists(self):
        """Test SpecRecord defaults list fields to empty lists."""
        now = datetime.now(UTC)
        record = SpecRecord(
            spec_index=0,
            purpose="Test",
            vision="Test",
            status="blocked",
            created_at=now,
            updated_at=now,
        )

        assert record.must == []
        assert record.dont == []
        assert record.nice == []
        assert record.assumptions == []
        assert record.history == []

    def test_spec_record_spec_index_validation(self):
        """Test SpecRecord validates spec_index is non-negative."""
        now = datetime.now(UTC)

        with pytest.raises(ValidationError) as exc_info:
            SpecRecord(
                spec_index=-1,
                purpose="Test",
                vision="Test",
                status="blocked",
                created_at=now,
                updated_at=now,
            )

        errors = exc_info.value.errors()
        assert any("spec_index" in str(e) for e in errors)

    def test_spec_record_execution_attempts_defaults_to_zero(self):
        """Test SpecRecord defaults execution_attempts to 0."""
        now = datetime.now(UTC)
        record = SpecRecord(
            spec_index=0,
            purpose="Test",
            vision="Test",
            status="blocked",
            created_at=now,
            updated_at=now,
        )

        assert record.execution_attempts == 0

    def test_spec_record_last_execution_at_defaults_to_none(self):
        """Test SpecRecord defaults last_execution_at to None."""
        now = datetime.now(UTC)
        record = SpecRecord(
            spec_index=0,
            purpose="Test",
            vision="Test",
            status="blocked",
            created_at=now,
            updated_at=now,
        )

        assert record.last_execution_at is None

    def test_spec_record_execution_attempts_with_value(self):
        """Test SpecRecord accepts positive execution_attempts."""
        now = datetime.now(UTC)
        record = SpecRecord(
            spec_index=0,
            purpose="Test",
            vision="Test",
            status="running",
            created_at=now,
            updated_at=now,
            execution_attempts=3,
        )

        assert record.execution_attempts == 3

    def test_spec_record_execution_attempts_rejects_negative(self):
        """Test SpecRecord validates execution_attempts is non-negative."""
        now = datetime.now(UTC)

        with pytest.raises(ValidationError) as exc_info:
            SpecRecord(
                spec_index=0,
                purpose="Test",
                vision="Test",
                status="blocked",
                created_at=now,
                updated_at=now,
                execution_attempts=-1,
            )

        errors = exc_info.value.errors()
        assert any("execution_attempts" in str(e) for e in errors)

    def test_spec_record_last_execution_at_with_timestamp(self):
        """Test SpecRecord accepts timezone-aware last_execution_at timestamp."""
        now = datetime.now(UTC)
        execution_time = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        record = SpecRecord(
            spec_index=0,
            purpose="Test",
            vision="Test",
            status="running",
            created_at=now,
            updated_at=now,
            execution_attempts=1,
            last_execution_at=execution_time,
        )

        assert record.last_execution_at == execution_time
        assert record.last_execution_at.tzinfo == UTC

    def test_spec_record_last_execution_at_converts_naive_to_utc(self):
        """Test SpecRecord converts naive last_execution_at to UTC."""
        now = datetime.now(UTC)
        naive_time = datetime(2025, 1, 15, 10, 30, 0)

        record = SpecRecord.model_validate(
            {
                "spec_index": 0,
                "purpose": "Test",
                "vision": "Test",
                "status": "running",
                "created_at": now,
                "updated_at": now,
                "execution_attempts": 1,
                "last_execution_at": naive_time,
            }
        )

        assert record.last_execution_at.tzinfo == UTC

    def test_spec_record_backward_compatibility_missing_execution_fields(self):
        """Test SpecRecord loads old documents without execution metadata fields."""
        now = datetime.now(UTC)

        # Simulate old document without execution metadata fields
        old_doc = {
            "spec_index": 0,
            "purpose": "Test",
            "vision": "Test",
            "status": "blocked",
            "created_at": now,
            "updated_at": now,
            "history": [],
        }

        record = SpecRecord.model_validate(old_doc)

        assert record.execution_attempts == 0
        assert record.last_execution_at is None

    def test_spec_record_serialization_includes_execution_fields(self):
        """Test SpecRecord serialization includes execution metadata fields."""
        now = datetime.now(UTC)
        execution_time = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        record = SpecRecord(
            spec_index=0,
            purpose="Test",
            vision="Test",
            status="running",
            created_at=now,
            updated_at=now,
            execution_attempts=2,
            last_execution_at=execution_time,
        )

        data = record.model_dump()
        assert "execution_attempts" in data
        assert "last_execution_at" in data
        assert data["execution_attempts"] == 2
        assert data["last_execution_at"] == execution_time


class TestPlanRecord:
    """Tests for PlanRecord model."""

    def test_plan_record_creation(self):
        """Test PlanRecord creation with all required fields."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())
        raw_request = {"id": plan_id, "specs": []}

        record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=5,
            completed_specs=0,
            current_spec_index=None,
            last_event_at=now,
            raw_request=raw_request,
        )

        assert record.plan_id == plan_id
        assert record.overall_status == "running"
        assert record.total_specs == 5
        assert record.completed_specs == 0
        assert record.current_spec_index is None
        assert record.raw_request == raw_request

    def test_plan_record_status_values(self):
        """Test PlanRecord accepts valid status values (no 'blocked')."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())
        valid_statuses = ["running", "finished", "failed"]

        for status in valid_statuses:
            record = PlanRecord(
                plan_id=plan_id,
                overall_status=status,
                created_at=now,
                updated_at=now,
                total_specs=1,
                last_event_at=now,
                raw_request={},
            )
            assert record.overall_status == status

    def test_plan_record_rejects_blocked_status(self):
        """Test PlanRecord rejects 'blocked' status (only for specs)."""
        now = datetime.now(UTC)

        with pytest.raises(ValidationError) as exc_info:
            PlanRecord(
                plan_id=str(uuid4()),
                overall_status="blocked",
                created_at=now,
                updated_at=now,
                total_specs=1,
                last_event_at=now,
                raw_request={},
            )

        errors = exc_info.value.errors()
        assert any("overall_status" in str(e) for e in errors)

    def test_plan_record_timezone_aware_timestamps(self):
        """Test PlanRecord ensures all timestamps are timezone-aware."""
        naive_dt = datetime(2025, 1, 1, 12, 0, 0)
        plan_id = str(uuid4())

        record = PlanRecord.model_validate(
            {
                "plan_id": plan_id,
                "overall_status": "running",
                "created_at": naive_dt,
                "updated_at": naive_dt,
                "total_specs": 1,
                "last_event_at": naive_dt,
                "raw_request": {},
            }
        )

        assert record.created_at.tzinfo == UTC
        assert record.updated_at.tzinfo == UTC
        assert record.last_event_at.tzinfo == UTC

    def test_plan_record_defaults_completed_specs_to_zero(self):
        """Test PlanRecord defaults completed_specs to 0."""
        now = datetime.now(UTC)
        record = PlanRecord(
            plan_id=str(uuid4()),
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=5,
            last_event_at=now,
            raw_request={},
        )

        assert record.completed_specs == 0

    def test_plan_record_current_spec_index_can_be_null(self):
        """Test PlanRecord allows current_spec_index to be None."""
        now = datetime.now(UTC)
        record = PlanRecord(
            plan_id=str(uuid4()),
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=5,
            current_spec_index=None,
            last_event_at=now,
            raw_request={},
        )

        assert record.current_spec_index is None

    def test_plan_record_validates_non_negative_counters(self):
        """Test PlanRecord validates counters are non-negative."""
        now = datetime.now(UTC)

        with pytest.raises(ValidationError) as exc_info:
            PlanRecord(
                plan_id=str(uuid4()),
                overall_status="running",
                created_at=now,
                updated_at=now,
                total_specs=-1,
                last_event_at=now,
                raw_request={},
            )

        errors = exc_info.value.errors()
        assert any("total_specs" in str(e) for e in errors)


class TestCreateInitialSpecRecord:
    """Tests for create_initial_spec_record factory helper."""

    def test_create_initial_spec_record_with_defaults(self):
        """Test creating initial spec record with default values."""
        spec_in = SpecIn(
            purpose="Test purpose",
            vision="Test vision",
            must=["must1"],
            dont=["dont1"],
            nice=["nice1"],
            assumptions=["assumption1"],
        )

        record = create_initial_spec_record(spec_in, spec_index=0)

        assert record.spec_index == 0
        assert record.purpose == "Test purpose"
        assert record.vision == "Test vision"
        assert record.must == ["must1"]
        assert record.dont == ["dont1"]
        assert record.nice == ["nice1"]
        assert record.assumptions == ["assumption1"]
        assert record.status == "blocked"
        assert record.created_at.tzinfo == UTC
        assert record.updated_at.tzinfo == UTC
        assert record.created_at == record.updated_at
        assert record.history == []

    def test_create_initial_spec_record_with_custom_status(self):
        """Test creating initial spec record with custom status."""
        spec_in = SpecIn(purpose="Test", vision="Test")

        record = create_initial_spec_record(spec_in, spec_index=1, status="running")

        assert record.status == "running"
        assert record.spec_index == 1

    def test_create_initial_spec_record_with_custom_timestamp(self):
        """Test creating initial spec record with custom timestamp."""
        spec_in = SpecIn(purpose="Test", vision="Test")
        custom_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        record = create_initial_spec_record(spec_in, spec_index=0, now=custom_time)

        assert record.created_at == custom_time
        assert record.updated_at == custom_time

    def test_create_initial_spec_record_converts_naive_timestamp_to_utc(self):
        """Test factory converts naive datetime to UTC."""
        spec_in = SpecIn(purpose="Test", vision="Test")
        naive_time = datetime(2025, 1, 1, 12, 0, 0)

        record = create_initial_spec_record(spec_in, spec_index=0, now=naive_time)

        assert record.created_at.tzinfo == UTC
        assert record.updated_at.tzinfo == UTC

    def test_create_initial_spec_record_rejects_invalid_status(self):
        """Test factory rejects invalid status values."""
        spec_in = SpecIn(purpose="Test", vision="Test")

        with pytest.raises(ValidationError) as exc_info:
            create_initial_spec_record(spec_in, spec_index=0, status="invalid")

        errors = exc_info.value.errors()
        assert any("status" in str(e) for e in errors)

    def test_create_initial_spec_record_copies_lists(self):
        """Test factory creates independent copies of list fields."""
        must_list = ["must1"]
        spec_in = SpecIn(purpose="Test", vision="Test", must=must_list)

        record = create_initial_spec_record(spec_in, spec_index=0)

        # Modify original list
        must_list.append("must2")

        # Record should have independent copy
        assert record.must == ["must1"]

    def test_create_initial_spec_record_with_empty_lists(self):
        """Test factory handles empty lists correctly."""
        spec_in = SpecIn(purpose="Test", vision="Test")

        record = create_initial_spec_record(spec_in, spec_index=0)

        assert record.must == []
        assert record.dont == []
        assert record.nice == []
        assert record.assumptions == []

    def test_create_initial_spec_record_initializes_execution_metadata(self):
        """Test factory initializes execution metadata fields with correct defaults."""
        spec_in = SpecIn(purpose="Test", vision="Test")

        record = create_initial_spec_record(spec_in, spec_index=0)

        assert record.execution_attempts == 0
        assert record.last_execution_at is None

    def test_create_initial_spec_record_execution_fields_in_serialized_output(self):
        """Test factory creates record with execution fields that serialize correctly."""
        spec_in = SpecIn(purpose="Test", vision="Test")

        record = create_initial_spec_record(spec_in, spec_index=0)
        data = record.model_dump()

        assert "execution_attempts" in data
        assert "last_execution_at" in data
        assert data["execution_attempts"] == 0
        assert data["last_execution_at"] is None


class TestCreateInitialPlanRecord:
    """Tests for create_initial_plan_record factory helper."""

    def test_create_initial_plan_record_with_defaults(self):
        """Test creating initial plan record with default values."""
        plan_id = str(uuid4())
        specs = [SpecIn(purpose=f"Purpose {i}", vision=f"Vision {i}") for i in range(3)]
        plan_in = PlanIn(id=plan_id, specs=specs)

        record = create_initial_plan_record(plan_in)

        assert record.plan_id == plan_id
        assert record.overall_status == "running"
        assert record.total_specs == 3
        assert record.completed_specs == 0
        assert record.current_spec_index is None
        assert record.created_at.tzinfo == UTC
        assert record.updated_at.tzinfo == UTC
        assert record.last_event_at.tzinfo == UTC
        assert record.created_at == record.updated_at == record.last_event_at
        assert "id" in record.raw_request
        assert "specs" in record.raw_request

    def test_create_initial_plan_record_with_custom_status(self):
        """Test creating initial plan record with custom status."""
        plan_id = str(uuid4())
        spec = SpecIn(purpose="Test", vision="Test")
        plan_in = PlanIn(id=plan_id, specs=[spec])

        record = create_initial_plan_record(plan_in, overall_status="finished")

        assert record.overall_status == "finished"

    def test_create_initial_plan_record_with_custom_timestamp(self):
        """Test creating initial plan record with custom timestamp."""
        plan_id = str(uuid4())
        spec = SpecIn(purpose="Test", vision="Test")
        plan_in = PlanIn(id=plan_id, specs=[spec])
        custom_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        record = create_initial_plan_record(plan_in, now=custom_time)

        assert record.created_at == custom_time
        assert record.updated_at == custom_time
        assert record.last_event_at == custom_time

    def test_create_initial_plan_record_converts_naive_timestamp_to_utc(self):
        """Test factory converts naive datetime to UTC."""
        plan_id = str(uuid4())
        spec = SpecIn(purpose="Test", vision="Test")
        plan_in = PlanIn(id=plan_id, specs=[spec])
        naive_time = datetime(2025, 1, 1, 12, 0, 0)

        record = create_initial_plan_record(plan_in, now=naive_time)

        assert record.created_at.tzinfo == UTC
        assert record.updated_at.tzinfo == UTC
        assert record.last_event_at.tzinfo == UTC

    def test_create_initial_plan_record_rejects_invalid_status(self):
        """Test factory rejects invalid status values."""
        plan_id = str(uuid4())
        spec = SpecIn(purpose="Test", vision="Test")
        plan_in = PlanIn(id=plan_id, specs=[spec])

        with pytest.raises(ValidationError) as exc_info:
            create_initial_plan_record(plan_in, overall_status="blocked")

        errors = exc_info.value.errors()
        assert any("overall_status" in str(e) for e in errors)

    def test_create_initial_plan_record_stores_raw_request(self):
        """Test factory stores the original request as dict."""
        plan_id = str(uuid4())
        specs = [SpecIn(purpose="Test", vision="Test", must=["item1"])]
        plan_in = PlanIn(id=plan_id, specs=specs)

        record = create_initial_plan_record(plan_in)

        assert record.raw_request["id"] == plan_id
        assert len(record.raw_request["specs"]) == 1
        assert record.raw_request["specs"][0]["purpose"] == "Test"
        assert record.raw_request["specs"][0]["must"] == ["item1"]

    def test_create_initial_plan_record_counts_specs_correctly(self):
        """Test factory counts total specs correctly."""
        plan_id = str(uuid4())
        specs = [SpecIn(purpose=f"Test {i}", vision=f"Vision {i}") for i in range(10)]
        plan_in = PlanIn(id=plan_id, specs=specs)

        record = create_initial_plan_record(plan_in)

        assert record.total_specs == 10
        assert record.completed_specs == 0


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_empty_arrays_serialize_as_lists_not_none(self):
        """Test that empty arrays always serialize as [], never None."""
        spec = SpecIn(purpose="Test", vision="Test")
        data = spec.model_dump()

        assert data["must"] == []
        assert data["dont"] == []
        assert data["nice"] == []
        assert data["assumptions"] == []

    def test_spec_history_tolerates_empty_list(self):
        """Test SpecRecord history can be empty."""
        now = datetime.now(UTC)
        record = SpecRecord(
            spec_index=0,
            purpose="Test",
            vision="Test",
            status="blocked",
            created_at=now,
            updated_at=now,
            history=[],
        )

        assert record.history == []
        assert isinstance(record.history, list)

    def test_timestamps_consistent_across_serialization(self):
        """Test timezone-aware timestamps serialize/deserialize consistently."""
        now = datetime.now(UTC)
        record = SpecRecord(
            spec_index=0,
            purpose="Test",
            vision="Test",
            status="blocked",
            created_at=now,
            updated_at=now,
        )

        # Serialize and deserialize
        data = record.model_dump()
        restored = SpecRecord.model_validate(data)

        assert restored.created_at == now
        assert restored.updated_at == now

    def test_uuid_validation_comprehensive(self):
        """Test comprehensive UUID validation scenarios."""
        spec = SpecIn(purpose="Test", vision="Test")

        # Valid UUIDs
        valid_uuids = [
            str(uuid4()),
            "550e8400-e29b-41d4-a716-446655440000",
            "550e8400-e29b-41d4-a716-446655440000".upper(),
        ]

        for valid_uuid in valid_uuids:
            plan = PlanIn(id=valid_uuid, specs=[spec])
            assert plan.id == valid_uuid

        # Invalid UUIDs
        invalid_uuids = ["not-a-uuid", "12345", "", "invalid-uuid-format", None]

        for invalid_uuid in invalid_uuids:
            with pytest.raises(ValidationError):
                if invalid_uuid is None:
                    PlanIn(specs=[spec])
                else:
                    PlanIn(id=invalid_uuid, specs=[spec])

    def test_multiple_specs_maintain_order(self):
        """Test that multiple specs maintain their order."""
        plan_id = str(uuid4())
        specs = [SpecIn(purpose=f"Purpose {i}", vision=f"Vision {i}") for i in range(20)]
        plan_in = PlanIn(id=plan_id, specs=specs)

        for i, spec in enumerate(plan_in.specs):
            assert spec.purpose == f"Purpose {i}"
            assert spec.vision == f"Vision {i}"


class TestSpecStatusOut:
    """Tests for SpecStatusOut response model."""

    def test_spec_status_out_creation_with_all_fields(self):
        """Test SpecStatusOut creation with all fields."""
        now = datetime.now(UTC)
        status_out = SpecStatusOut(
            spec_index=0,
            status="running",
            stage="implementation",
            updated_at=now,
        )

        assert status_out.spec_index == 0
        assert status_out.status == "running"
        assert status_out.stage == "implementation"
        assert status_out.updated_at == now

    def test_spec_status_out_accepts_all_valid_statuses(self):
        """Test SpecStatusOut accepts all valid status values."""
        now = datetime.now(UTC)
        valid_statuses = ["blocked", "running", "finished", "failed"]

        for status in valid_statuses:
            status_out = SpecStatusOut(
                spec_index=0,
                status=status,
                updated_at=now,
            )
            assert status_out.status == status

    def test_spec_status_out_rejects_invalid_status(self):
        """Test SpecStatusOut rejects invalid status values."""
        now = datetime.now(UTC)

        with pytest.raises(ValidationError) as exc_info:
            SpecStatusOut(
                spec_index=0,
                status="invalid",
                updated_at=now,
            )

        errors = exc_info.value.errors()
        assert any("status" in str(e) for e in errors)
        # Enum validation error message
        assert any("enum" in str(e).lower() for e in errors)

    def test_spec_status_out_stage_is_optional(self):
        """Test SpecStatusOut allows stage to be None."""
        now = datetime.now(UTC)
        status_out = SpecStatusOut(
            spec_index=0,
            status="running",
            updated_at=now,
        )

        assert status_out.stage is None

    def test_spec_status_out_validates_non_negative_spec_index(self):
        """Test SpecStatusOut rejects negative spec_index."""
        now = datetime.now(UTC)

        with pytest.raises(ValidationError) as exc_info:
            SpecStatusOut(
                spec_index=-1,
                status="running",
                updated_at=now,
            )

        errors = exc_info.value.errors()
        assert any("spec_index" in str(e) for e in errors)

    def test_spec_status_out_converts_naive_datetime_to_utc(self):
        """Test SpecStatusOut converts naive datetime to UTC."""
        naive_dt = datetime(2025, 1, 1, 12, 0, 0)

        status_out = SpecStatusOut.model_validate(
            {
                "spec_index": 0,
                "status": "running",
                "updated_at": naive_dt,
            }
        )

        assert status_out.updated_at.tzinfo == UTC

    def test_spec_status_out_preserves_timezone_aware_datetime(self):
        """Test SpecStatusOut preserves timezone-aware datetime."""
        aware_dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        status_out = SpecStatusOut(
            spec_index=0,
            status="running",
            updated_at=aware_dt,
        )

        assert status_out.updated_at.tzinfo == UTC
        assert status_out.updated_at == aware_dt

    def test_spec_status_out_serialization(self):
        """Test SpecStatusOut serializes correctly."""
        now = datetime.now(UTC)
        status_out = SpecStatusOut(
            spec_index=2,
            status="finished",
            stage="reviewing",
            updated_at=now,
        )

        data = status_out.model_dump()
        assert data["spec_index"] == 2
        assert data["status"] == "finished"
        assert data["stage"] == "reviewing"
        assert data["updated_at"] == now

    def test_spec_status_out_serialization_with_none_stage(self):
        """Test SpecStatusOut serialization when stage is None."""
        now = datetime.now(UTC)
        status_out = SpecStatusOut(
            spec_index=0,
            status="blocked",
            updated_at=now,
        )

        data = status_out.model_dump()
        assert data["stage"] is None


class TestPlanStatusOut:
    """Tests for PlanStatusOut response model."""

    def test_plan_status_out_creation_with_all_fields(self):
        """Test PlanStatusOut creation with all fields."""
        now = datetime.now(UTC)
        spec1 = SpecStatusOut(spec_index=0, status="finished", updated_at=now)
        spec2 = SpecStatusOut(spec_index=1, status="running", updated_at=now)

        status_out = PlanStatusOut(
            plan_id=str(uuid4()),
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=2,
            completed_specs=1,
            current_spec_index=1,
            specs=[spec1, spec2],
        )

        assert status_out.total_specs == 2
        assert status_out.completed_specs == 1
        assert status_out.current_spec_index == 1
        assert len(status_out.specs) == 2

    def test_plan_status_out_accepts_all_valid_statuses(self):
        """Test PlanStatusOut accepts all valid overall_status values."""
        now = datetime.now(UTC)
        valid_statuses = ["running", "finished", "failed"]

        for status in valid_statuses:
            status_out = PlanStatusOut(
                plan_id=str(uuid4()),
                overall_status=status,
                created_at=now,
                updated_at=now,
                total_specs=1,
                completed_specs=0,
                specs=[],
            )
            assert status_out.overall_status == status

    def test_plan_status_out_rejects_invalid_overall_status(self):
        """Test PlanStatusOut rejects invalid overall_status values."""
        now = datetime.now(UTC)

        with pytest.raises(ValidationError) as exc_info:
            PlanStatusOut(
                plan_id=str(uuid4()),
                overall_status="blocked",
                created_at=now,
                updated_at=now,
                total_specs=1,
                completed_specs=0,
                specs=[],
            )

        errors = exc_info.value.errors()
        assert any("overall_status" in str(e) for e in errors)
        # Enum validation error message
        assert any("enum" in str(e).lower() for e in errors)

    def test_plan_status_out_rejects_invalid_status_string(self):
        """Test PlanStatusOut rejects invalid status string."""
        now = datetime.now(UTC)

        with pytest.raises(ValidationError) as exc_info:
            PlanStatusOut(
                plan_id=str(uuid4()),
                overall_status="invalid",
                created_at=now,
                updated_at=now,
                total_specs=1,
                completed_specs=0,
                specs=[],
            )

        errors = exc_info.value.errors()
        # Enum validation error message
        assert any("enum" in str(e).lower() for e in errors)

    def test_plan_status_out_current_spec_index_can_be_none(self):
        """Test PlanStatusOut allows current_spec_index to be None."""
        now = datetime.now(UTC)
        status_out = PlanStatusOut(
            plan_id=str(uuid4()),
            overall_status="finished",
            created_at=now,
            updated_at=now,
            total_specs=1,
            completed_specs=1,
            current_spec_index=None,
            specs=[],
        )

        assert status_out.current_spec_index is None

    def test_plan_status_out_converts_naive_datetimes_to_utc(self):
        """Test PlanStatusOut converts naive datetimes to UTC."""
        naive_dt = datetime(2025, 1, 1, 12, 0, 0)

        status_out = PlanStatusOut.model_validate(
            {
                "plan_id": str(uuid4()),
                "overall_status": "running",
                "created_at": naive_dt,
                "updated_at": naive_dt,
                "total_specs": 1,
                "completed_specs": 0,
                "specs": [],
            }
        )

        assert status_out.created_at.tzinfo == UTC
        assert status_out.updated_at.tzinfo == UTC

    def test_plan_status_out_validates_non_negative_counters(self):
        """Test PlanStatusOut validates counters are non-negative."""
        now = datetime.now(UTC)

        with pytest.raises(ValidationError) as exc_info:
            PlanStatusOut(
                plan_id=str(uuid4()),
                overall_status="running",
                created_at=now,
                updated_at=now,
                total_specs=-1,
                completed_specs=0,
                specs=[],
            )

        errors = exc_info.value.errors()
        assert any("total_specs" in str(e) for e in errors)

    def test_plan_status_out_from_records_basic(self):
        """Test PlanStatusOut.from_records with basic scenario."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        # Create plan record
        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=2,
            completed_specs=0,
            current_spec_index=0,
            last_event_at=now,
            raw_request={},
        )

        # Create spec records
        spec_records = [
            SpecRecord(
                spec_index=0,
                purpose="Test 1",
                vision="Vision 1",
                status="running",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=1,
                purpose="Test 2",
                vision="Vision 2",
                status="blocked",
                created_at=now,
                updated_at=now,
            ),
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records)

        assert status_out.plan_id == plan_id
        assert status_out.overall_status == "running"
        assert status_out.total_specs == 2
        assert status_out.completed_specs == 0
        assert status_out.current_spec_index == 0
        assert len(status_out.specs) == 2
        assert status_out.specs[0].spec_index == 0
        assert status_out.specs[0].status == "running"
        assert status_out.specs[1].spec_index == 1
        assert status_out.specs[1].status == "blocked"

    def test_plan_status_out_from_records_computes_completed_specs(self):
        """Test PlanStatusOut.from_records correctly computes completed_specs."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=5,
            last_event_at=now,
            raw_request={},
        )

        spec_records = [
            SpecRecord(
                spec_index=i,
                purpose=f"Test {i}",
                vision=f"Vision {i}",
                status="finished" if i < 3 else ("running" if i == 3 else "blocked"),
                created_at=now,
                updated_at=now,
            )
            for i in range(5)
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records)

        assert status_out.completed_specs == 3

    def test_plan_status_out_from_records_computes_current_spec_index(self):
        """Test PlanStatusOut.from_records correctly computes current_spec_index."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=3,
            last_event_at=now,
            raw_request={},
        )

        spec_records = [
            SpecRecord(
                spec_index=0,
                purpose="Test 0",
                vision="Vision 0",
                status="finished",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=1,
                purpose="Test 1",
                vision="Vision 1",
                status="running",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=2,
                purpose="Test 2",
                vision="Vision 2",
                status="blocked",
                created_at=now,
                updated_at=now,
            ),
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records)

        assert status_out.current_spec_index == 1

    def test_plan_status_out_from_records_current_spec_index_none_when_no_running(self):
        """Test PlanStatusOut.from_records sets current_spec_index to None when no running spec."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="finished",
            created_at=now,
            updated_at=now,
            total_specs=2,
            last_event_at=now,
            raw_request={},
        )

        spec_records = [
            SpecRecord(
                spec_index=0,
                purpose="Test 0",
                vision="Vision 0",
                status="finished",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=1,
                purpose="Test 1",
                vision="Vision 1",
                status="finished",
                created_at=now,
                updated_at=now,
            ),
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records)

        assert status_out.current_spec_index is None

    def test_plan_status_out_from_records_with_current_stage(self):
        """Test PlanStatusOut.from_records includes current_stage from spec records."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=1,
            last_event_at=now,
            raw_request={},
        )

        spec_records = [
            SpecRecord(
                spec_index=0,
                purpose="Test",
                vision="Vision",
                status="running",
                current_stage="implementation",
                created_at=now,
                updated_at=now,
            ),
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records)

        assert status_out.specs[0].stage == "implementation"

    def test_plan_status_out_from_records_with_none_current_stage(self):
        """Test PlanStatusOut.from_records handles None current_stage."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=1,
            last_event_at=now,
            raw_request={},
        )

        spec_records = [
            SpecRecord(
                spec_index=0,
                purpose="Test",
                vision="Vision",
                status="blocked",
                created_at=now,
                updated_at=now,
            ),
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records)

        assert status_out.specs[0].stage is None

    def test_plan_status_out_serialization(self):
        """Test PlanStatusOut serializes correctly."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())
        spec1 = SpecStatusOut(spec_index=0, status="finished", updated_at=now)

        status_out = PlanStatusOut(
            plan_id=plan_id,
            overall_status="finished",
            created_at=now,
            updated_at=now,
            total_specs=1,
            completed_specs=1,
            current_spec_index=None,
            specs=[spec1],
        )

        data = status_out.model_dump()
        assert data["plan_id"] == plan_id
        assert data["overall_status"] == "finished"
        assert data["total_specs"] == 1
        assert data["completed_specs"] == 1
        assert data["current_spec_index"] is None
        assert len(data["specs"]) == 1

    def test_plan_status_out_from_records_with_multi_spec_ordering(self):
        """Test PlanStatusOut.from_records maintains spec_index ordering."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=5,
            last_event_at=now,
            raw_request={},
        )

        # Create specs in random order but with spec_index set
        spec_records = [
            SpecRecord(
                spec_index=2,
                purpose="Spec 2",
                vision="Vision 2",
                status="blocked",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=0,
                purpose="Spec 0",
                vision="Vision 0",
                status="finished",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=4,
                purpose="Spec 4",
                vision="Vision 4",
                status="blocked",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=1,
                purpose="Spec 1",
                vision="Vision 1",
                status="running",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=3,
                purpose="Spec 3",
                vision="Vision 3",
                status="blocked",
                created_at=now,
                updated_at=now,
            ),
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records)

        # Verify specs are returned in the same order as input (function does not sort)
        # Caller is responsible for providing specs ordered by spec_index
        assert len(status_out.specs) == 5
        assert status_out.specs[0].spec_index == 2
        assert status_out.specs[1].spec_index == 0
        assert status_out.specs[2].spec_index == 4
        assert status_out.specs[3].spec_index == 1
        assert status_out.specs[4].spec_index == 3

    def test_plan_status_out_from_records_completed_specs_accuracy(self):
        """Test PlanStatusOut.from_records accurately counts completed specs."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=7,
            last_event_at=now,
            raw_request={},
        )

        # Mix of finished, running, blocked, and failed specs
        spec_records = [
            SpecRecord(
                spec_index=i,
                purpose=f"Spec {i}",
                vision=f"Vision {i}",
                status=(
                    "finished"
                    if i < 3
                    else ("running" if i == 3 else ("failed" if i == 4 else "blocked"))
                ),
                created_at=now,
                updated_at=now,
            )
            for i in range(7)
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records)

        # Only specs 0, 1, 2 are finished
        assert status_out.completed_specs == 3
        assert status_out.total_specs == 7

    def test_plan_status_out_from_records_current_spec_index_derivation(self):
        """Test PlanStatusOut.from_records finds first running spec for current_spec_index."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=4,
            last_event_at=now,
            raw_request={},
        )

        # Multiple running specs - should return first one
        spec_records = [
            SpecRecord(
                spec_index=0,
                purpose="Spec 0",
                vision="Vision 0",
                status="finished",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=1,
                purpose="Spec 1",
                vision="Vision 1",
                status="finished",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=2,
                purpose="Spec 2",
                vision="Vision 2",
                status="running",  # First running spec
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=3,
                purpose="Spec 3",
                vision="Vision 3",
                status="blocked",
                created_at=now,
                updated_at=now,
            ),
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records)

        # Should find spec 2 as current
        assert status_out.current_spec_index == 2

    def test_plan_status_out_from_records_include_stage_toggle_true(self):
        """Test PlanStatusOut.from_records includes stage when include_stage=True."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=2,
            last_event_at=now,
            raw_request={},
        )

        spec_records = [
            SpecRecord(
                spec_index=0,
                purpose="Spec 0",
                vision="Vision 0",
                status="running",
                current_stage="implementation",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=1,
                purpose="Spec 1",
                vision="Vision 1",
                status="blocked",
                current_stage=None,
                created_at=now,
                updated_at=now,
            ),
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records, include_stage=True)

        # Stage values should be included
        assert status_out.specs[0].stage == "implementation"
        assert status_out.specs[1].stage is None

    def test_plan_status_out_from_records_include_stage_toggle_false(self):
        """Test PlanStatusOut.from_records omits stage when include_stage=False."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=2,
            last_event_at=now,
            raw_request={},
        )

        spec_records = [
            SpecRecord(
                spec_index=0,
                purpose="Spec 0",
                vision="Vision 0",
                status="running",
                current_stage="implementation",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=1,
                purpose="Spec 1",
                vision="Vision 1",
                status="blocked",
                current_stage="reviewing",
                created_at=now,
                updated_at=now,
            ),
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records, include_stage=False)

        # Stage values should be None even though current_stage is set
        assert status_out.specs[0].stage is None
        assert status_out.specs[1].stage is None

    def test_plan_status_out_from_records_no_running_spec(self):
        """Test PlanStatusOut.from_records sets current_spec_index to None when no running spec."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="finished",
            created_at=now,
            updated_at=now,
            total_specs=3,
            last_event_at=now,
            raw_request={},
        )

        # All specs finished or blocked, no running spec
        spec_records = [
            SpecRecord(
                spec_index=0,
                purpose="Spec 0",
                vision="Vision 0",
                status="finished",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=1,
                purpose="Spec 1",
                vision="Vision 1",
                status="finished",
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=2,
                purpose="Spec 2",
                vision="Vision 2",
                status="finished",
                created_at=now,
                updated_at=now,
            ),
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records)

        # No running spec, so current_spec_index should be None
        assert status_out.current_spec_index is None

    def test_plan_status_out_from_records_all_specs_finished(self):
        """Test PlanStatusOut.from_records with all specs finished."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="finished",
            created_at=now,
            updated_at=now,
            total_specs=3,
            last_event_at=now,
            raw_request={},
        )

        spec_records = [
            SpecRecord(
                spec_index=i,
                purpose=f"Spec {i}",
                vision=f"Vision {i}",
                status="finished",
                created_at=now,
                updated_at=now,
            )
            for i in range(3)
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records)

        # All specs are finished
        assert status_out.completed_specs == 3
        assert status_out.total_specs == 3
        assert status_out.current_spec_index is None
        assert status_out.overall_status == "finished"

    def test_plan_status_out_from_records_empty_specs_list(self):
        """Test PlanStatusOut.from_records with empty specs list."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=0,
            last_event_at=now,
            raw_request={},
        )

        status_out = PlanStatusOut.from_records(plan_record, [])

        # Empty specs
        assert status_out.total_specs == 0
        assert status_out.completed_specs == 0
        assert status_out.current_spec_index is None
        assert len(status_out.specs) == 0

    def test_plan_status_out_from_records_stage_propagation_from_pubsub(self):
        """Test that stage data from Pub/Sub updates is preserved in response."""
        now = datetime.now(UTC)
        plan_id = str(uuid4())

        plan_record = PlanRecord(
            plan_id=plan_id,
            overall_status="running",
            created_at=now,
            updated_at=now,
            total_specs=3,
            last_event_at=now,
            raw_request={},
        )

        # Simulate specs with current_stage from Pub/Sub updates
        spec_records = [
            SpecRecord(
                spec_index=0,
                purpose="Spec 0",
                vision="Vision 0",
                status="finished",
                current_stage="completed",  # From Pub/Sub
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=1,
                purpose="Spec 1",
                vision="Vision 1",
                status="running",
                current_stage="implementation",  # From Pub/Sub
                created_at=now,
                updated_at=now,
            ),
            SpecRecord(
                spec_index=2,
                purpose="Spec 2",
                vision="Vision 2",
                status="blocked",
                current_stage=None,  # No stage yet
                created_at=now,
                updated_at=now,
            ),
        ]

        status_out = PlanStatusOut.from_records(plan_record, spec_records, include_stage=True)

        # Stage data should be propagated
        assert status_out.specs[0].stage == "completed"
        assert status_out.specs[1].stage == "implementation"
        assert status_out.specs[2].stage is None


class TestStatusEnums:
    """Tests for status enums."""

    def test_spec_status_enum_values(self):
        """Test SpecStatus enum has correct values."""
        assert SpecStatus.BLOCKED.value == "blocked"
        assert SpecStatus.RUNNING.value == "running"
        assert SpecStatus.FINISHED.value == "finished"
        assert SpecStatus.FAILED.value == "failed"

    def test_plan_status_enum_values(self):
        """Test PlanStatus enum has correct values."""
        assert PlanStatus.RUNNING.value == "running"
        assert PlanStatus.FINISHED.value == "finished"
        assert PlanStatus.FAILED.value == "failed"

    def test_spec_status_enum_has_no_blocked(self):
        """Test PlanStatus enum does not have BLOCKED."""
        assert not hasattr(PlanStatus, "BLOCKED")
