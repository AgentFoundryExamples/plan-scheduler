# Plan Ingestion Models

This module contains canonical request/response schemas and internal storage records for plan ingestion.

## Overview

The plan ingestion system uses Pydantic models to validate incoming requests and prepare data for Firestore storage. The models are split into two categories:

1. **Request/Response Models**: API contract definitions for external communication
2. **Storage Records**: Internal representations with metadata for Firestore persistence

## Request/Response Models

### SpecIn

Input specification model matching the required contract.

```python
from app.models import SpecIn

spec = SpecIn(
    purpose="Implement user authentication",
    vision="Secure and scalable auth system",
    must=["JWT tokens", "Password hashing"],
    dont=["Plain text passwords"],
    nice=["OAuth integration"],
    assumptions=["Users have email addresses"]
)
```

**Fields:**
- `purpose` (str, required): Purpose of the specification
- `vision` (str, required): Vision for the specification
- `must` (list[str]): Required features/constraints (defaults to empty list)
- `dont` (list[str]): Things to avoid (defaults to empty list)
- `nice` (list[str]): Nice-to-have features (defaults to empty list)
- `assumptions` (list[str]): Assumptions made (defaults to empty list)

**Validation:**
- All list fields must serialize as lists (never None or missing)
- Empty lists are allowed

### PlanIn

Input plan model with UUID validation.

```python
from app.models import PlanIn
from uuid import uuid4

plan = PlanIn(
    id=str(uuid4()),
    specs=[spec1, spec2, spec3]
)
```

**Fields:**
- `id` (str, required): Plan ID as UUID string
- `specs` (list[SpecIn], required): List of specifications

**Validation:**
- `id` must be a valid UUID string
- At least one SpecIn must be provided

### PlanCreateResponse

Response model for plan creation API.

```python
from app.models import PlanCreateResponse

response = PlanCreateResponse(
    plan_id="550e8400-e29b-41d4-a716-446655440000",
    status="running"
)
```

**Fields:**
- `plan_id` (str, required): Plan ID
- `status` (str, required): Plan status (running|finished|failed)

## Storage Records

### SpecRecord

Internal record for storing specification data in Firestore with execution metadata.

```python
from app.models import create_initial_spec_record

spec_record = create_initial_spec_record(
    spec_in=spec,
    spec_index=0,
    status="blocked"  # optional, defaults to "blocked"
)
```

**Fields:**
- `spec_index` (int): Index of this spec in the plan (0-based)
- `purpose`, `vision`, `must`, `dont`, `nice`, `assumptions`: Copied from SpecIn
- `status` (str): Spec status (blocked|running|finished|failed)
- `created_at` (datetime): UTC timestamp when spec was created
- `updated_at` (datetime): UTC timestamp when spec was last updated
- `history` (list[dict]): State transition history (empty initially)

**Status Values:**
- `blocked`: Spec is waiting for dependencies or prerequisites
- `running`: Spec is currently being executed
- `finished`: Spec completed successfully
- `failed`: Spec execution failed

### PlanRecord

Internal record for storing plan data in Firestore with execution metadata.

```python
from app.models import create_initial_plan_record

plan_record = create_initial_plan_record(
    plan_in=plan,
    overall_status="running"  # optional, defaults to "running"
)
```

**Fields:**
- `plan_id` (str): Plan ID as UUID string
- `overall_status` (str): Overall plan status (running|finished|failed)
- `created_at` (datetime): UTC timestamp when plan was created
- `updated_at` (datetime): UTC timestamp when plan was last updated
- `total_specs` (int): Total number of specs in the plan
- `completed_specs` (int): Number of completed specs (defaults to 0)
- `current_spec_index` (int | None): Index of currently running spec (null if none)
- `last_event_at` (datetime): UTC timestamp of last event/update
- `raw_request` (dict): Original plan request payload for audit/replay

**Status Values:**
- `running`: Plan is currently being executed
- `finished`: Plan completed successfully
- `failed`: Plan execution failed

**Note:** PlanRecord does not include "blocked" status (only individual specs can be blocked).

## Factory Helpers

### create_initial_spec_record()

Creates an initial SpecRecord from SpecIn with consistent defaults.

```python
from app.models import create_initial_spec_record
from datetime import datetime, UTC

record = create_initial_spec_record(
    spec_in=spec,
    spec_index=0,
    status="blocked",  # optional
    now=datetime.now(UTC)  # optional
)
```

**Parameters:**
- `spec_in` (SpecIn): The input specification model
- `spec_index` (int): The index of this spec in the plan (0-based)
- `status` (str, optional): Initial status (default: "blocked")
- `now` (datetime, optional): Timestamp to use (default: current UTC time)

**Features:**
- Ensures timezone-aware timestamps (UTC)
- Creates independent copies of list fields
- Initializes empty history list
- Validates status values

### create_initial_plan_record()

Creates an initial PlanRecord from PlanIn with consistent defaults.

```python
from app.models import create_initial_plan_record
from datetime import datetime, UTC

record = create_initial_plan_record(
    plan_in=plan,
    overall_status="running",  # optional
    now=datetime.now(UTC)  # optional
)
```

**Parameters:**
- `plan_in` (PlanIn): The input plan model
- `overall_status` (str, optional): Initial overall status (default: "running")
- `now` (datetime, optional): Timestamp to use (default: current UTC time)

**Features:**
- Ensures timezone-aware timestamps (UTC)
- Automatically counts total specs
- Initializes completed_specs to 0
- Stores raw request payload
- Sets current_spec_index to None

## Usage Examples

### Complete Flow

```python
from app.models import (
    SpecIn,
    PlanIn,
    PlanCreateResponse,
    create_initial_spec_record,
    create_initial_plan_record,
)
from uuid import uuid4

# 1. Create input models
specs = [
    SpecIn(
        purpose="Implement authentication",
        vision="Secure auth system",
        must=["JWT", "Hashing"],
        dont=["Plain passwords"],
        nice=["OAuth"],
        assumptions=[]
    ),
    SpecIn(
        purpose="Add logging",
        vision="Comprehensive logging",
        must=["JSON format"],
        dont=[],
        nice=["Aggregation"],
        assumptions=[]
    )
]

plan_in = PlanIn(id=str(uuid4()), specs=specs)

# 2. Create storage records
spec_records = [
    create_initial_spec_record(spec, idx)
    for idx, spec in enumerate(plan_in.specs)
]

plan_record = create_initial_plan_record(plan_in)

# 3. Create API response
response = PlanCreateResponse(
    plan_id=plan_record.plan_id,
    status=plan_record.overall_status
)

# 4. Store in Firestore (future implementation)
# firestore_client.collection("plans").document(plan_record.plan_id).set(
#     plan_record.model_dump()
# )
```

## Edge Cases & Best Practices

### Empty Lists
All list fields (must, dont, nice, assumptions) can be empty but will always serialize as `[]`, never `None`:

```python
spec = SpecIn(purpose="Test", vision="Test")
assert spec.must == []
assert spec.dont == []
```

### UUID Validation
Plan IDs are validated as UUID strings. Invalid UUIDs are rejected early:

```python
# Valid
plan = PlanIn(id=str(uuid4()), specs=[spec])

# Invalid - raises ValidationError
plan = PlanIn(id="not-a-uuid", specs=[spec])
```

### Timezone-Aware Timestamps
All timestamps are automatically converted to UTC if naive:

```python
from datetime import datetime

naive_dt = datetime(2025, 1, 1, 12, 0, 0)
record = create_initial_spec_record(spec, 0, now=naive_dt)
assert record.created_at.tzinfo == timezone.utc
```

### List Independence
Factory helpers create independent copies of lists to prevent mutations:

```python
must_list = ["item1"]
spec = SpecIn(purpose="Test", vision="Test", must=must_list)
record = create_initial_spec_record(spec, 0)

must_list.append("item2")  # Won't affect record
assert record.must == ["item1"]
```

## Testing

Comprehensive test coverage is available in `tests/test_plan_models.py`:

```bash
# Run model tests
poetry run pytest tests/test_plan_models.py -v

# Run with coverage
poetry run pytest tests/test_plan_models.py --cov=app.models
```

## See Also

- [Firestore Service Documentation](../services/firestore_service.py)
- [API Endpoints](../api/) (future implementation)
- [Project README](../../README.md)
