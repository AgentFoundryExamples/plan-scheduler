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

Comprehensive test coverage is available in `tests/test_plan_models.py` and `tests/test_pubsub_models.py`:

```bash
# Run model tests
poetry run pytest tests/test_plan_models.py -v
poetry run pytest tests/test_pubsub_models.py -v

# Run with coverage
poetry run pytest tests/test_plan_models.py tests/test_pubsub_models.py --cov=app.models
```

## Pub/Sub Models

This section documents the Pub/Sub payload models used for spec status updates.

### Overview

The Pub/Sub integration uses a two-layer structure:
1. **Outer Envelope**: `PubSubPushEnvelope` - Standard Google Cloud Pub/Sub push format
2. **Inner Payload**: `SpecStatusPayload` - Application-specific spec status data

All models enforce that `plan_id` and `spec_index` are present to ensure downstream services can always resolve the relevant spec for updates.

### SpecStatusPayload

The decoded inner payload containing spec execution status information.

```python
from app.models.pubsub import SpecStatusPayload

payload = SpecStatusPayload(
    plan_id="550e8400-e29b-41d4-a716-446655440000",
    spec_index=0,
    status="finished",
    stage="implementation"  # optional
)
```

**Fields:**

- `plan_id` (str, **required**): UUID string identifying the plan. Must be present for spec resolution.
- `spec_index` (int, **required**): Zero-based index of the spec within the plan. Must be >= 0. Required for spec resolution.
- `status` (str, **required**): Current status of spec execution. Must be one of:
  - `"blocked"` - Waiting for dependencies
  - `"running"` - Currently executing
  - `"finished"` - Completed successfully
  - `"failed"` - Execution failed
- `stage` (str, **optional**): Execution stage/phase information for progress tracking (e.g., "analyzing", "implementing", "testing", "reviewing")

**Validation:**
- `plan_id` must be a non-empty string (UUID format validated at API level)
- `spec_index` must be a non-negative integer
- `status` must match the regex pattern: `^(blocked|running|finished|failed)$`
- `stage` is optional and can be any string

**Usage Notes:**
- **Terminal Statuses**: `"finished"` and `"failed"` trigger state machine transitions
- **Intermediate Statuses**: `"blocked"` and `"running"` with stage update `current_stage` field
- Execution services **must** include both `plan_id` and `spec_index` in every status update
- `stage` is useful for tracking progress within a spec execution (e.g., multiple phases)

### PubSubMessage

The message object within the Pub/Sub push envelope.

```python
from app.models.pubsub import PubSubMessage

message = PubSubMessage(
    data="eyJwbGFuX2lkIjoiNTUwZTg0MDAtZTI5Yi00MWQ0LWE3MTYtNDQ2NjU1NDQwMDAwIiwic3BlY19pbmRleCI6MCwic3RhdHVzIjoiZmluaXNoZWQifQ==",
    messageId="1234567890",
    publishTime="2025-01-01T12:00:00Z",
    attributes={"key": "value"}
)
```

**Fields:**

- `data` (str, **required**): Base64-encoded message payload containing SpecStatusPayload JSON
- `attributes` (dict[str, str]): Optional key-value metadata attached to the message (defaults to empty dict)
- `messageId` (str): Unique identifier for this message assigned by Pub/Sub (defaults to empty string)
- `publishTime` (str): RFC3339 timestamp when message was published (defaults to empty string)

**Validation:**
- `publishTime` accepts both string and datetime objects, converts to ISO format string
- `data` must be valid base64-encoded UTF-8 JSON

**Usage Notes:**
- `messageId` is used for deduplication - the service tracks processed messageIds in history
- `publishTime` is informational and used for logging/debugging
- `attributes` can be used for routing or filtering in advanced Pub/Sub configurations

### PubSubPushEnvelope

Outer envelope for Pub/Sub push subscription requests.

```python
from app.models.pubsub import PubSubPushEnvelope, PubSubMessage

envelope = PubSubPushEnvelope(
    message=PubSubMessage(
        data="base64-encoded-payload",
        messageId="msg-123",
        publishTime="2025-01-01T12:00:00Z",
        attributes={}
    ),
    subscription="projects/my-project/subscriptions/my-sub"
)
```

**Fields:**

- `message` (PubSubMessage, **required**): The Pub/Sub message object containing data and metadata
- `subscription` (str): Full resource name of the subscription (defaults to empty string)
  - Format: `"projects/{project}/subscriptions/{subscription}"`

**Validation:**
- `message` must be a valid PubSubMessage object
- `subscription` is optional but typically provided by Pub/Sub

**Usage Notes:**
- This model matches the exact JSON structure sent by Google Cloud Pub/Sub push subscriptions
- The actual application payload is nested within `message.data` as base64-encoded JSON
- `subscription` is useful for logging and routing in multi-subscription scenarios

### decode_pubsub_message()

Helper function to decode and parse base64-encoded Pub/Sub message payloads.

```python
from app.models.pubsub import decode_pubsub_message
import base64
import json

# Encode a payload
payload = {"plan_id": "abc-123", "spec_index": 0, "status": "running"}
encoded = base64.b64encode(json.dumps(payload).encode()).decode()

# Decode the message
decoded = decode_pubsub_message(encoded)
print(decoded)  # {"plan_id": "abc-123", "spec_index": 0, "status": "running"}
```

**Parameters:**
- `encoded_data` (str): Base64-encoded string from message.data field

**Returns:**
- `dict[str, Any]`: Parsed JSON payload as a dictionary

**Raises:**
- `ValueError`: If base64 decoding fails, JSON parsing fails, or decoded data is not a JSON object

**Error Messages:**
The function provides descriptive error messages for common failure cases:
- Empty or missing data: `"Message data is empty or missing"`
- Invalid base64: `"Failed to decode base64 message data: {error}"`
- Invalid UTF-8: `"Failed to decode message as UTF-8: {error}"`
- Invalid JSON: `"Failed to parse message as JSON: {error}"`
- Non-object JSON: `"Message payload must be a JSON object, got {type}"`

**Usage Notes:**
- This helper is used internally by the Pub/Sub endpoint
- Execution services should use standard base64 encoding: `base64.b64encode(json.dumps(payload).encode()).decode()`
- Ensure JSON is properly formatted before encoding

### Complete Pub/Sub Integration Example

```python
import base64
import json
from app.models.pubsub import (
    SpecStatusPayload,
    PubSubMessage,
    PubSubPushEnvelope,
    decode_pubsub_message,
)

# 1. Execution service creates status payload
status_payload = SpecStatusPayload(
    plan_id="550e8400-e29b-41d4-a716-446655440000",
    spec_index=0,
    status="finished",
    stage="implementation"
)

# 2. Encode payload for Pub/Sub
payload_json = status_payload.model_dump_json()
encoded_data = base64.b64encode(payload_json.encode()).decode()

# 3. Pub/Sub wraps in push envelope (done by Pub/Sub service)
envelope = PubSubPushEnvelope(
    message=PubSubMessage(
        data=encoded_data,
        messageId="unique-msg-id-123",
        publishTime="2025-01-01T12:00:00Z",
        attributes={}
    ),
    subscription="projects/test-project/subscriptions/test-sub"
)

# 4. Plan Scheduler receives and processes
# Decode the message
decoded_dict = decode_pubsub_message(envelope.message.data)

# Validate against schema
payload = SpecStatusPayload(**decoded_dict)

print(f"Processing status update: plan={payload.plan_id}, spec={payload.spec_index}, status={payload.status}")
# Output: Processing status update: plan=550e8400-e29b-41d4-a716-446655440000, spec=0, status=finished
```

### Status Transition Examples

**Example 1: Finishing a Spec**

```python
from app.models.pubsub import SpecStatusPayload

# Execution service reports spec completion
payload = SpecStatusPayload(
    plan_id="550e8400-e29b-41d4-a716-446655440000",
    spec_index=0,
    status="finished"
    # stage is optional for terminal statuses
)

# Plan Scheduler will:
# 1. Mark spec 0 as finished
# 2. Increment completed_specs counter
# 3. Unblock spec 1 (blocked -> running)
# 4. Trigger execution for spec 1
```

**Example 2: Reporting Progress with Stages**

```python
from app.models.pubsub import SpecStatusPayload

# Execution service reports intermediate progress
progress_payloads = [
    SpecStatusPayload(
        plan_id="550e8400-e29b-41d4-a716-446655440000",
        spec_index=1,
        status="running",
        stage="analyzing"
    ),
    SpecStatusPayload(
        plan_id="550e8400-e29b-41d4-a716-446655440000",
        spec_index=1,
        status="running",
        stage="implementing"
    ),
    SpecStatusPayload(
        plan_id="550e8400-e29b-41d4-a716-446655440000",
        spec_index=1,
        status="running",
        stage="testing"
    ),
]

# Plan Scheduler will:
# 1. Update current_stage field to "analyzing", "implementing", "testing"
# 2. Append each update to history
# 3. Keep main status as "running"
# 4. NOT trigger any state machine transitions
```

**Example 3: Manual Retry After Failure**

```python
from app.models.pubsub import SpecStatusPayload

# Initial failure
failure = SpecStatusPayload(
    plan_id="550e8400-e29b-41d4-a716-446655440000",
    spec_index=2,
    status="failed"
)
# Plan is marked as failed

# Manual intervention: Re-emit status to retry
# Note: This requires re-creating the spec with status="running" first
retry_attempt = SpecStatusPayload(
    plan_id="550e8400-e29b-41d4-a716-446655440000",
    spec_index=2,
    status="running",
    stage="retry-attempt-2"
)

# Eventually succeed
success = SpecStatusPayload(
    plan_id="550e8400-e29b-41d4-a716-446655440000",
    spec_index=2,
    status="finished"
)

# Note: Manual retries require careful orchestration
# - Cannot transition from "failed" back to "running" automatically
# - May require manual Firestore updates or admin intervention
# - Consider implementing a retry endpoint for operational flexibility
```

**Example 4: Out-of-Order Prevention**

```python
from app.models.pubsub import SpecStatusPayload

# Spec 1 is currently running (current_spec_index=1)
# Spec 2 is blocked

# Attempt to finish spec 2 before spec 1
invalid_payload = SpecStatusPayload(
    plan_id="550e8400-e29b-41d4-a716-446655440000",
    spec_index=2,
    status="finished"
)

# Plan Scheduler will:
# 1. Detect out-of-order completion (spec 2 finishing while current_spec_index=1)
# 2. Reject the update (transaction aborted)
# 3. Log error with diagnostic information
# 4. Return 204 No Content (graceful handling)
# 5. NOT update any state

# Action required: Investigate upstream execution service
```

### Edge Cases

**Duplicate messageIds:**
```python
# Same messageId sent twice (Pub/Sub retry)
payload = SpecStatusPayload(plan_id="abc", spec_index=0, status="finished")

# First request: Processed successfully, messageId stored in history
# Second request: Detected as duplicate, skipped, returns 204 No Content
```

**Stage-only updates:**
```python
# Status without stage - stage field remains unchanged
payload1 = SpecStatusPayload(plan_id="abc", spec_index=0, status="running")

# Status with stage - stage field updated
payload2 = SpecStatusPayload(plan_id="abc", spec_index=0, status="running", stage="testing")

# Both update history, but only payload2 updates current_stage
```

**Terminal status protection:**
```python
# Spec is already finished
# Attempt to finish again (duplicate or race condition)
duplicate = SpecStatusPayload(plan_id="abc", spec_index=0, status="finished")

# Plan Scheduler will:
# 1. Detect spec is already in terminal state
# 2. Reject the duplicate terminal status
# 3. Log warning
# 4. Return 204 No Content (graceful handling)
```

## See Also

- [Firestore Service Documentation](../services/firestore_service.py)
- [API Endpoints](../api/) (future implementation)
- [Project README](../../README.md)
- [Pub/Sub API Endpoint](../api/pubsub.py)
