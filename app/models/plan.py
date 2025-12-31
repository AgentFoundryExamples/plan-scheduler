"""Plan ingestion schemas and internal storage records.

This module defines:
1. Request/response schemas (SpecIn, PlanIn, PlanCreateResponse) for API contracts
2. Internal record definitions (SpecRecord, PlanRecord) for Firestore storage
3. Factory helpers for creating initial records with consistent defaults

Status Values:
- SpecRecord.status: "blocked" | "running" | "finished" | "failed"
- PlanRecord.overall_status: "running" | "finished" | "failed"
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


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
    history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="History of state transitions (can be empty initially)",
    )

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def ensure_timezone_aware(cls, v: Any) -> datetime:
        """Ensure timestamps are timezone-aware (UTC)."""
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=UTC)
            return v
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
        SpecRecord with consistent defaults and timezone-aware timestamps

    Raises:
        ValueError: If status is not one of: blocked, running, finished, failed
    """
    if status not in ("blocked", "running", "finished", "failed"):
        raise ValueError(
            f"Invalid spec status: {status}. Must be one of: blocked, running, finished, failed"
        )

    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    return SpecRecord(
        spec_index=spec_index,
        purpose=spec_in.purpose,
        vision=spec_in.vision,
        must=spec_in.must.copy() if spec_in.must else [],
        dont=spec_in.dont.copy() if spec_in.dont else [],
        nice=spec_in.nice.copy() if spec_in.nice else [],
        assumptions=spec_in.assumptions.copy() if spec_in.assumptions else [],
        status=status,
        created_at=now,
        updated_at=now,
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
        ValueError: If overall_status is not one of: running, finished, failed
    """
    if overall_status not in ("running", "finished", "failed"):
        raise ValueError(
            f"Invalid plan status: {overall_status}. Must be one of: running, finished, failed"
        )

    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    return PlanRecord(
        plan_id=plan_in.id,
        overall_status=overall_status,
        created_at=now,
        updated_at=now,
        total_specs=len(plan_in.specs),
        completed_specs=0,
        current_spec_index=None,
        last_event_at=now,
        raw_request=plan_in.model_dump(),
    )
