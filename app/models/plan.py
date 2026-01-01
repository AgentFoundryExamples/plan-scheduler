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
"""Plan ingestion schemas and internal storage records.

This module defines:
1. Request/response schemas (SpecIn, PlanIn, PlanCreateResponse) for API contracts
2. Status response schemas (SpecStatusOut, PlanStatusOut) for status query endpoints
3. Internal record definitions (SpecRecord, PlanRecord) for Firestore storage
4. Factory helpers for creating initial records with consistent defaults

Status Values:
- SpecRecord.status: "blocked" | "running" | "finished" | "failed"
- PlanRecord.overall_status: "running" | "finished" | "failed"
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class SpecStatus(str, Enum):
    """Valid spec status values."""

    BLOCKED = "blocked"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


class PlanStatus(str, Enum):
    """Valid plan status values."""

    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


class SpecIn(BaseModel):
    """
    Specification input model matching the required contract.

    All list fields must be present and serialize as lists (never None or missing).
    Empty lists are allowed but fields cannot be omitted.
    """

    purpose: str = Field(..., description="Purpose of the specification")
    vision: str = Field(..., description="Vision for the specification")
    must: list[str] = Field(
        default_factory=list, description="Required features/constraints (can be empty)"
    )
    dont: list[str] = Field(default_factory=list, description="Things to avoid (can be empty)")
    nice: list[str] = Field(
        default_factory=list, description="Nice-to-have features (can be empty)"
    )
    assumptions: list[str] = Field(
        default_factory=list, description="Assumptions made (can be empty)"
    )

    @field_validator("must", "dont", "nice", "assumptions", mode="before")
    @classmethod
    def ensure_list_not_none(cls, v: Any) -> list[str]:
        """Ensure list fields are never None, convert to empty list if needed."""
        if v is None:
            return []
        return v


class PlanIn(BaseModel):
    """
    Plan input model with UUID validation.

    The plan id must be a valid UUID string.
    At least one SpecIn must be provided in the specs list.
    """

    id: str = Field(..., description="Plan ID as UUID string")
    specs: list[SpecIn] = Field(..., description="List of specifications")

    @field_validator("id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        """Validate that id is a valid UUID string."""
        try:
            UUID(v)
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid UUID string: {v}") from e
        return v

    @model_validator(mode="after")
    def validate_at_least_one_spec(self) -> "PlanIn":
        """Ensure at least one specification is present."""
        if not self.specs or len(self.specs) == 0:
            raise ValueError("At least one specification must be provided")
        return self


class SpecStatusOut(BaseModel):
    """
    Response model for spec status queries.

    Provides a lightweight status view of a spec without exposing internal details
    like purpose, vision, or history. Only includes execution state and progress metadata.

    All timestamps are timezone-aware (UTC).
    """

    spec_index: int = Field(..., description="Index of the spec in the plan", ge=0)
    status: str = Field(
        ...,
        description="Spec status: blocked, running, finished, or failed",
    )
    stage: str | None = Field(
        default=None,
        description="Optional execution stage/phase (e.g., 'implementation', 'reviewing')",
    )
    updated_at: datetime = Field(..., description="Timestamp when spec was last updated (UTC)")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status is one of the supported values."""
        valid_statuses = {s.value for s in SpecStatus}
        if v not in valid_statuses:
            raise ValueError(f"Invalid spec status: {v}. Must be one of {sorted(valid_statuses)}")
        return v

    @field_validator("spec_index")
    @classmethod
    def validate_spec_index(cls, v: int) -> int:
        """Validate spec_index is non-negative."""
        if v < 0:
            raise ValueError("spec_index must be non-negative")
        return v

    @field_validator("updated_at", mode="before")
    @classmethod
    def ensure_timezone_aware(cls, v: Any) -> datetime:
        """Ensure updated_at is timezone-aware (UTC)."""
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=UTC)
            return v
        return v


class PlanStatusOut(BaseModel):
    """
    Response model for plan status queries.

    Provides complete plan status including all spec statuses. Designed for
    status polling and progress tracking by external integrators.

    Helper methods compute completed_specs and current_spec_index from the specs list
    to ensure consistency and avoid duplicating logic in API handlers.

    All timestamps are timezone-aware (UTC).
    """

    plan_id: str = Field(..., description="Plan identifier as UUID string")
    overall_status: str = Field(
        ...,
        description="Overall plan status: running, finished, or failed",
    )
    created_at: datetime = Field(..., description="Timestamp when plan was created (UTC)")
    updated_at: datetime = Field(..., description="Timestamp when plan was last updated (UTC)")
    total_specs: int = Field(..., description="Total number of specs in the plan", ge=0)
    completed_specs: int = Field(..., description="Number of completed specs", ge=0)
    current_spec_index: int | None = Field(
        default=None,
        description="Index of the currently running spec (null if none running)",
    )
    specs: list[SpecStatusOut] = Field(..., description="List of spec statuses")

    @field_validator("overall_status")
    @classmethod
    def validate_overall_status(cls, v: str) -> str:
        """Validate overall_status is one of the supported values."""
        valid_statuses = {s.value for s in PlanStatus}
        if v not in valid_statuses:
            raise ValueError(f"Invalid plan status: {v}. Must be one of {sorted(valid_statuses)}")
        return v

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def ensure_timezone_aware(cls, v: Any) -> datetime:
        """Ensure timestamps are timezone-aware (UTC)."""
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=UTC)
            return v
        return v

    @classmethod
    def from_records(
        cls,
        plan_record: "PlanRecord",
        spec_records: list["SpecRecord"],
    ) -> "PlanStatusOut":
        """
        Helper to construct PlanStatusOut from PlanRecord and SpecRecords.

        Automatically computes completed_specs and current_spec_index from the
        spec records to ensure consistency.

        Args:
            plan_record: The plan record from Firestore
            spec_records: List of spec records from Firestore (should be sorted by spec_index)

        Returns:
            PlanStatusOut with all fields populated correctly
        """
        # Convert spec records to status out
        spec_statuses = [
            SpecStatusOut(
                spec_index=spec.spec_index,
                status=spec.status,
                stage=getattr(spec, "current_stage", None),
                updated_at=spec.updated_at,
            )
            for spec in spec_records
        ]

        # Compute completed_specs
        completed_specs = sum(1 for spec in spec_records if spec.status == "finished")

        # Compute current_spec_index (first running spec, or None if none)
        current_spec_index = None
        for spec in spec_records:
            if spec.status == "running":
                current_spec_index = spec.spec_index
                break

        return cls(
            plan_id=plan_record.plan_id,
            overall_status=plan_record.overall_status,
            created_at=plan_record.created_at,
            updated_at=plan_record.updated_at,
            total_specs=plan_record.total_specs,
            completed_specs=completed_specs,
            current_spec_index=current_spec_index,
            specs=spec_statuses,
        )


class PlanCreateResponse(BaseModel):
    """
    Response model for plan creation API.

    Status is limited to: "running" | "finished" | "failed"
    """

    plan_id: str = Field(..., description="Plan ID")
    status: str = Field(
        ...,
        description="Plan status: running, finished, or failed",
        pattern="^(running|finished|failed)$",
    )


class SpecRecord(BaseModel):
    """
    Internal record for storing specification data in Firestore.

    This model includes the original SpecIn fields plus metadata for tracking
    execution state, timestamps, and history.

    Status Values:
        - "blocked": Spec is waiting for dependencies or prerequisites
        - "running": Spec is currently being executed
        - "finished": Spec completed successfully
        - "failed": Spec execution failed

    Execution Metadata:
        - execution_attempts: Number of times execution has been triggered
          (updated by trigger_spec_execution)
        - last_execution_at: Timestamp of most recent execution trigger
          (updated by trigger_spec_execution)

    Timestamps are timezone-aware (UTC) to avoid serialization mismatches.
    """

    spec_index: int = Field(..., description="Index of this spec in the plan", ge=0)
    purpose: str = Field(..., description="Purpose of the specification")
    vision: str = Field(..., description="Vision for the specification")
    must: list[str] = Field(default_factory=list, description="Required features/constraints")
    dont: list[str] = Field(default_factory=list, description="Things to avoid")
    nice: list[str] = Field(default_factory=list, description="Nice-to-have features")
    assumptions: list[str] = Field(default_factory=list, description="Assumptions made")
    status: str = Field(
        ...,
        description="Spec status: blocked, running, finished, or failed",
        pattern="^(blocked|running|finished|failed)$",
    )
    created_at: datetime = Field(..., description="Timestamp when spec was created (UTC)")
    updated_at: datetime = Field(..., description="Timestamp when spec was last updated (UTC)")
    execution_attempts: int = Field(
        default=0,
        description=(
            "Number of times execution has been triggered " "(updated by trigger_spec_execution)"
        ),
        ge=0,
    )
    last_execution_at: datetime | None = Field(
        default=None,
        description=(
            "Timestamp of most recent execution trigger " "(updated by trigger_spec_execution, UTC)"
        ),
    )
    current_stage: str | None = Field(
        default=None,
        description="Optional execution stage/phase (e.g., 'implementation', 'reviewing')",
    )
    history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="History of state transitions (can be empty initially)",
    )

    @field_validator("created_at", "updated_at", "last_execution_at", mode="after")
    @classmethod
    def ensure_timezone_aware(cls, v: datetime | None) -> datetime | None:
        """Ensure timestamps are timezone-aware (UTC)."""
        if v is None:
            return None
        if v.tzinfo is None:
            return v.replace(tzinfo=UTC)
        return v


class PlanRecord(BaseModel):
    """
    Internal record for storing plan data in Firestore.

    This model includes metadata for tracking overall plan execution state,
    progress counters, timestamps, and the original request payload.

    Overall Status Values:
        - "running": Plan is currently being executed
        - "finished": Plan completed successfully
        - "failed": Plan execution failed

    Note: PlanRecord does not include "blocked" status (only individual specs can be blocked).

    Timestamps are timezone-aware (UTC) to avoid serialization mismatches.
    """

    plan_id: str = Field(..., description="Plan ID as UUID string")
    overall_status: str = Field(
        ...,
        description="Overall plan status: running, finished, or failed",
        pattern="^(running|finished|failed)$",
    )
    created_at: datetime = Field(..., description="Timestamp when plan was created (UTC)")
    updated_at: datetime = Field(..., description="Timestamp when plan was last updated (UTC)")
    total_specs: int = Field(..., description="Total number of specs in the plan", ge=0)
    completed_specs: int = Field(default=0, description="Number of completed specs", ge=0)
    current_spec_index: int | None = Field(
        default=None,
        description="Index of the currently running spec (null if none running)",
    )
    last_event_at: datetime = Field(..., description="Timestamp of the last event/update (UTC)")
    raw_request: dict[str, Any] = Field(
        ..., description="Original plan request payload for audit/replay"
    )

    @field_validator("created_at", "updated_at", "last_event_at", mode="before")
    @classmethod
    def ensure_timezone_aware(cls, v: Any) -> datetime:
        """Ensure timestamps are timezone-aware (UTC)."""
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=UTC)
            return v
        return v


def create_initial_spec_record(
    spec_in: SpecIn,
    spec_index: int,
    status: str = "blocked",
    now: datetime | None = None,
) -> SpecRecord:
    """
    Factory helper to create an initial SpecRecord from SpecIn.

    Args:
        spec_in: The input specification model
        spec_index: The index of this spec in the plan (0-based)
        status: Initial status (default: "blocked")
        now: Optional timestamp to use (default: current UTC time)

    Returns:
        SpecRecord with consistent defaults and timezone-aware timestamps.
        Execution metadata fields (execution_attempts, last_execution_at) are
        initialized to default values (0 and None respectively).

    Raises:
        pydantic.ValidationError: If status is invalid
    """
    timestamp = now if now is not None else datetime.now(UTC)

    return SpecRecord(
        spec_index=spec_index,
        purpose=spec_in.purpose,
        vision=spec_in.vision,
        must=spec_in.must.copy(),
        dont=spec_in.dont.copy(),
        nice=spec_in.nice.copy(),
        assumptions=spec_in.assumptions.copy(),
        status=status,
        created_at=timestamp,
        updated_at=timestamp,
        execution_attempts=0,
        last_execution_at=None,
        history=[],
    )


def create_initial_plan_record(
    plan_in: PlanIn,
    overall_status: str = "running",
    now: datetime | None = None,
) -> PlanRecord:
    """
    Factory helper to create an initial PlanRecord from PlanIn.

    Args:
        plan_in: The input plan model
        overall_status: Initial overall status (default: "running")
        now: Optional timestamp to use (default: current UTC time)

    Returns:
        PlanRecord with consistent defaults and timezone-aware timestamps

    Raises:
        pydantic.ValidationError: If overall_status is invalid
    """
    timestamp = now if now is not None else datetime.now(UTC)

    return PlanRecord(
        plan_id=plan_in.id,
        overall_status=overall_status,
        created_at=timestamp,
        updated_at=timestamp,
        total_specs=len(plan_in.specs),
        completed_specs=0,
        current_spec_index=None,
        last_event_at=timestamp,
        raw_request=plan_in.model_dump(),
    )
