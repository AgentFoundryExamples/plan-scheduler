# Manual End-to-End Testing Guide

This guide provides step-by-step instructions for manually testing the Plan Scheduler service end-to-end, including creating plans, simulating Pub/Sub notifications, monitoring logs, and verifying completion.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Test Environment Setup](#test-environment-setup)
- [End-to-End Test Scenario](#end-to-end-test-scenario)
- [Simulating Pub/Sub Push Payloads](#simulating-pubsub-push-payloads)
- [Monitoring and Observability](#monitoring-and-observability)
- [Verifying Plan Completion](#verifying-plan-completion)
- [Failure Mode Testing](#failure-mode-testing)
- [Common Troubleshooting Scenarios](#common-troubleshooting-scenarios)
- [Automated Test Script](#automated-test-script)

## Prerequisites

Before running manual tests, ensure you have:

- Plan Scheduler service deployed and running (locally or on Cloud Run)
- `curl` or similar HTTP client installed
- `jq` for JSON parsing (optional but recommended)
- Access to service logs (local terminal or `gcloud` CLI)
- Service URL (e.g., `http://localhost:8080` or Cloud Run URL)

### Environment Variables

Set these for convenience:

```bash
# Local development
export SERVICE_URL=http://localhost:8080

# Cloud Run
export SERVICE_URL=https://plan-scheduler-abc123-uc.a.run.app

# For Pub/Sub testing - Generate a secure token or retrieve from Secret Manager
# Option 1: Generate new token for testing
export VERIFICATION_TOKEN=$(openssl rand -base64 32)

# Option 2: Retrieve from Secret Manager (Cloud Run)
export VERIFICATION_TOKEN=$(gcloud secrets versions access latest --secret=pubsub-verification-token)

# Option 3: Use token from .env file (local development)
export VERIFICATION_TOKEN=$(grep PUBSUB_VERIFICATION_TOKEN .env | cut -d '=' -f2)
```

## Test Environment Setup

### Option 1: Local Development

Start the service locally:

```bash
# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Start the service
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# In a separate terminal, monitor logs
# Logs will appear in the terminal where uvicorn is running
```

### Option 2: Cloud Run

Deploy to Cloud Run (see [Cloud Run Deployment Guide](./cloud-run.md)) and get the service URL:

```bash
export PROJECT_ID=your-project-id
export REGION=us-central1

# Get service URL
export SERVICE_URL=$(gcloud run services describe plan-scheduler \
  --region=${REGION} \
  --format='value(status.url)')

echo "Service URL: ${SERVICE_URL}"
```

### Verify Service Health

Before testing, confirm the service is healthy:

```bash
# Test health endpoint
curl -i ${SERVICE_URL}/health

# Expected response:
# HTTP/1.1 200 OK
# Content-Type: application/json
# {"status":"ok"}
```

## End-to-End Test Scenario

This section walks through a complete manual test scenario from plan creation to completion.

### Step 1: Create a Test Plan

Create a plan with three specifications:

```bash
# Generate a unique plan ID
PLAN_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
echo "Testing with plan ID: ${PLAN_ID}"

# Create the plan
curl -X POST ${SERVICE_URL}/plans \
  -H "Content-Type: application/json" \
  -d '{
    "id": "'${PLAN_ID}'",
    "specs": [
      {
        "purpose": "Design database schema",
        "vision": "Create normalized tables for user and post data",
        "must": ["Primary keys", "Foreign key constraints"],
        "dont": ["Use NoSQL", "Denormalize"],
        "nice": ["Add indexes for common queries"],
        "assumptions": ["PostgreSQL 14 or higher"]
      },
      {
        "purpose": "Implement REST API",
        "vision": "Build CRUD endpoints for users and posts",
        "must": ["Authentication", "Input validation"],
        "dont": ["Allow SQL injection"],
        "nice": ["API versioning"],
        "assumptions": ["FastAPI framework"]
      },
      {
        "purpose": "Write unit tests",
        "vision": "Achieve 80% code coverage",
        "must": ["Test all endpoints", "Mock external dependencies"],
        "dont": ["Test implementation details"],
        "nice": ["Parameterized tests"],
        "assumptions": ["pytest framework"]
      }
    ]
  }'

# Expected response (201 Created):
# {"plan_id":"550e8400-...", "status":"running"}
```

### Step 2: Verify Plan Creation

Check that the plan was created successfully:

```bash
# Query plan status
curl -i ${SERVICE_URL}/plans/${PLAN_ID} | jq

# Expected response (200 OK):
# {
#   "plan_id": "550e8400-...",
#   "overall_status": "running",
#   "total_specs": 3,
#   "completed_specs": 0,
#   "current_spec_index": 0,
#   "created_at": "2025-01-01T12:00:00Z",
#   "updated_at": "2025-01-01T12:00:00Z",
#   "specs": [
#     {
#       "spec_index": 0,
#       "status": "running",
#       "stage": null,
#       "updated_at": "2025-01-01T12:00:00Z"
#     },
#     {
#       "spec_index": 1,
#       "status": "blocked",
#       "stage": null,
#       "updated_at": "2025-01-01T12:00:00Z"
#     },
#     {
#       "spec_index": 2,
#       "status": "blocked",
#       "stage": null,
#       "updated_at": "2025-01-01T12:00:00Z"
#     }
#   ]
# }
```

**What to verify:**
- ✅ Plan status is `"running"`
- ✅ First spec (index 0) has status `"running"`
- ✅ Remaining specs (index 1, 2) have status `"blocked"`
- ✅ `current_spec_index` is `0`
- ✅ `completed_specs` is `0`

## Simulating Pub/Sub Push Payloads

The service receives status updates via Pub/Sub push notifications. To test manually, we simulate these payloads.

### Understanding Pub/Sub Push Format

Pub/Sub sends messages in this envelope structure:

```json
{
  "message": {
    "data": "<base64-encoded-payload>",
    "messageId": "unique-message-id",
    "publishTime": "2025-01-01T12:00:00Z",
    "attributes": {}
  },
  "subscription": "projects/project-id/subscriptions/subscription-name"
}
```

The `data` field contains base64-encoded JSON with the actual status update.

### Step 3: Send Intermediate Status Update (Optional)

Simulate a progress update for spec 0:

```bash
# Create the status payload
PAYLOAD='{"plan_id":"'${PLAN_ID}'","spec_index":0,"status":"running","stage":"implementation"}'

# Encode as base64
ENCODED=$(echo -n "$PAYLOAD" | base64)

# Send Pub/Sub push request
curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
  -d '{
    "message": {
      "data": "'${ENCODED}'",
      "messageId": "test-msg-001",
      "publishTime": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    },
    "subscription": "projects/test-project/subscriptions/test-sub"
  }'

# Expected response: 204 No Content (empty body)
```

**Verify in logs:**
- Look for `"event_type": "non_terminal_update"`
- Spec 0 `current_stage` updated to `"implementation"`
- Main `status` remains `"running"`

### Step 4: Complete Spec 0

Send a terminal status update to mark spec 0 as finished:

```bash
# Create the completion payload
PAYLOAD='{"plan_id":"'${PLAN_ID}'","spec_index":0,"status":"finished"}'

# Encode as base64
ENCODED=$(echo -n "$PAYLOAD" | base64)

# Send Pub/Sub push request
curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
  -d '{
    "message": {
      "data": "'${ENCODED}'",
      "messageId": "test-msg-002",
      "publishTime": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    },
    "subscription": "projects/test-project/subscriptions/test-sub"
  }'

# Expected response: 204 No Content
```

**Verify the state transition:**

```bash
curl ${SERVICE_URL}/plans/${PLAN_ID} | jq

# Expected changes:
# - spec 0: status = "finished"
# - spec 1: status = "running" (unblocked)
# - spec 2: status = "blocked" (unchanged)
# - completed_specs = 1
# - current_spec_index = 1
```

### Step 5: Complete Spec 1

Progress through spec 1:

```bash
# Send intermediate updates (optional)
PAYLOAD='{"plan_id":"'${PLAN_ID}'","spec_index":1,"status":"running","stage":"testing"}'
ENCODED=$(echo -n "$PAYLOAD" | base64)
curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
  -d '{
    "message": {
      "data": "'${ENCODED}'",
      "messageId": "test-msg-003",
      "publishTime": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    },
    "subscription": "projects/test-project/subscriptions/test-sub"
  }'

# Mark spec 1 as finished
PAYLOAD='{"plan_id":"'${PLAN_ID}'","spec_index":1,"status":"finished"}'
ENCODED=$(echo -n "$PAYLOAD" | base64)
curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
  -d '{
    "message": {
      "data": "'${ENCODED}'",
      "messageId": "test-msg-004",
      "publishTime": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    },
    "subscription": "projects/test-project/subscriptions/test-sub"
  }'
```

**Verify:**

```bash
curl ${SERVICE_URL}/plans/${PLAN_ID} | jq

# Expected:
# - spec 0: status = "finished"
# - spec 1: status = "finished"
# - spec 2: status = "running" (unblocked)
# - completed_specs = 2
# - current_spec_index = 2
```

### Step 6: Complete Spec 2 (Final Spec)

Complete the last spec:

```bash
# Mark spec 2 as finished
PAYLOAD='{"plan_id":"'${PLAN_ID}'","spec_index":2,"status":"finished"}'
ENCODED=$(echo -n "$PAYLOAD" | base64)
curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
  -d '{
    "message": {
      "data": "'${ENCODED}'",
      "messageId": "test-msg-005",
      "publishTime": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
    },
    "subscription": "projects/test-project/subscriptions/test-sub"
  }'
```

**Verify plan completion:**

```bash
curl ${SERVICE_URL}/plans/${PLAN_ID} | jq

# Expected:
# - overall_status = "finished"
# - spec 0, 1, 2: status = "finished"
# - completed_specs = 3
# - current_spec_index = null (no spec running)
```

## Monitoring and Observability

### Viewing Logs

#### Local Development

Logs appear in the terminal where uvicorn is running:

```bash
# Logs are automatically printed to stdout
# Look for structured JSON log entries with fields like:
# - timestamp
# - level (INFO, WARNING, ERROR)
# - message
# - plan_id, spec_index
# - event_type (terminal_spec_finished, non_terminal_update, etc.)
```

#### Cloud Run

```bash
# View recent logs
gcloud run services logs read plan-scheduler \
  --region=${REGION} \
  --limit=50

# Stream logs in real-time
gcloud run services logs tail plan-scheduler \
  --region=${REGION}

# Filter by plan_id
gcloud run services logs read plan-scheduler \
  --region=${REGION} \
  --log-filter='jsonPayload.plan_id="'${PLAN_ID}'"'

# Filter by severity
gcloud run services logs read plan-scheduler \
  --region=${REGION} \
  --log-filter='severity>=WARNING'
```

### Key Log Events to Monitor

| Event Type | Log Level | Description | What to Check |
|------------|-----------|-------------|---------------|
| `terminal_spec_finished` | INFO | Spec completed | Verify spec transitioned to "finished" |
| `terminal_plan_finished` | INFO | All specs done | Verify plan overall_status = "finished" |
| `terminal_spec_failed` | ERROR | Spec failed | Verify spec transitioned to "failed" |
| `non_terminal_update` | INFO | Progress update | Verify current_stage updated |
| Authentication success | INFO | Request authenticated | Verify auth method (OIDC/token) |
| Authentication failure | WARNING | Auth failed | Check credentials |
| Duplicate message | WARNING | Idempotency hit | Normal - message was retried |
| Out-of-order event | ERROR | Ordering violation | Investigate execution logic |

### Example Log Entry

```json
{
  "timestamp": "2025-01-01T12:30:00Z",
  "level": "INFO",
  "service": "plan-scheduler",
  "message": "Terminal status update: spec finished",
  "plan_id": "550e8400-e29b-41d4-a716-446655440000",
  "spec_index": 0,
  "status": "finished",
  "is_terminal": true,
  "event_type": "terminal_spec_finished",
  "message_id": "test-msg-002",
  "correlation_id": null
}
```

## Verifying Plan Completion

### Using the Status Endpoint

Query the plan status endpoint to verify final state:

```bash
# Get plan status
curl ${SERVICE_URL}/plans/${PLAN_ID} | jq

# Verify completion criteria:
# ✅ overall_status = "finished"
# ✅ completed_specs = total_specs
# ✅ current_spec_index = null
# ✅ All specs have status = "finished"
```

### Using the API Documentation

Navigate to the interactive API docs:

```bash
# Open in browser
echo "API Docs: ${SERVICE_URL}/docs"

# Or use curl
curl ${SERVICE_URL}/docs
```

In Swagger UI:
1. Expand `GET /plans/{plan_id}`
2. Click "Try it out"
3. Enter your plan ID
4. Click "Execute"
5. Verify response shows all specs completed

## Failure Mode Testing

Test how the service handles various failure scenarios.

### Test 1: Missing Authentication

Attempt to send a Pub/Sub request without authentication:

```bash
# Send request without verification token
curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "data": "'${ENCODED}'",
      "messageId": "test-msg-unauth"
    }
  }'

# Expected response: 401 Unauthorized
# {"detail":"Invalid or missing authentication"}
```

**What to verify:**
- ✅ Response is 401 Unauthorized
- ✅ Logs show authentication failure
- ✅ Plan state is unchanged

### Test 2: Invalid Verification Token

Send a request with wrong token:

```bash
curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -H "x-goog-pubsub-verification-token: wrong-token" \
  -d '{
    "message": {
      "data": "'${ENCODED}'",
      "messageId": "test-msg-wrong-token"
    }
  }'

# Expected response: 401 Unauthorized
```

**What to verify:**
- ✅ Response is 401 Unauthorized
- ✅ Logs show token mismatch
- ✅ No state changes occurred

### Test 3: Spec Failure

Simulate a spec failure:

```bash
# Create a new plan for failure testing
FAIL_PLAN_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

curl -X POST ${SERVICE_URL}/plans \
  -H "Content-Type: application/json" \
  -d '{
    "id": "'${FAIL_PLAN_ID}'",
    "specs": [
      {"purpose": "Test failure", "vision": "Should fail"},
      {"purpose": "Should not run", "vision": "Blocked by failure"}
    ]
  }'

# Mark spec 0 as failed
PAYLOAD='{"plan_id":"'${FAIL_PLAN_ID}'","spec_index":0,"status":"failed","details":"Execution timeout"}'
ENCODED=$(echo -n "$PAYLOAD" | base64)

curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
  -d '{
    "message": {
      "data": "'${ENCODED}'",
      "messageId": "test-msg-fail-001"
    }
  }'

# Verify failure handling
curl ${SERVICE_URL}/plans/${FAIL_PLAN_ID} | jq

# Expected:
# - overall_status = "failed"
# - spec 0: status = "failed"
# - spec 1: status = "blocked" (never unblocked)
# - current_spec_index = null
```

**What to verify:**
- ✅ Plan overall_status = "failed"
- ✅ Failed spec has status = "failed"
- ✅ Remaining specs stay "blocked"
- ✅ No further execution triggered
- ✅ Logs show `terminal_spec_failed` event

### Test 4: Invalid Payload

Send malformed payload:

```bash
# Invalid base64
curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
  -d '{
    "message": {
      "data": "not-valid-base64!@#$",
      "messageId": "test-msg-invalid"
    }
  }'

# Expected response: 400 Bad Request
# {"detail":"Invalid base64 encoding"}
```

**What to verify:**
- ✅ Response is 400 Bad Request
- ✅ Logs show decoding error
- ✅ No state changes occurred

### Test 5: Missing Required Fields

Send payload with missing fields:

```bash
# Missing spec_index
PAYLOAD='{"plan_id":"'${PLAN_ID}'","status":"finished"}'
ENCODED=$(echo -n "$PAYLOAD" | base64)

curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
  -d '{
    "message": {
      "data": "'${ENCODED}'",
      "messageId": "test-msg-missing-field"
    }
  }'

# Expected response: 400 Bad Request with validation error
```

**What to verify:**
- ✅ Response is 400 Bad Request
- ✅ Error details specify missing field
- ✅ No state changes occurred

### Test 6: Out-of-Order Completion

Attempt to complete specs out of order:

```bash
# Create a new plan
OOO_PLAN_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')

curl -X POST ${SERVICE_URL}/plans \
  -H "Content-Type: application/json" \
  -d '{
    "id": "'${OOO_PLAN_ID}'",
    "specs": [
      {"purpose": "Spec 0", "vision": "First"},
      {"purpose": "Spec 1", "vision": "Second"},
      {"purpose": "Spec 2", "vision": "Third"}
    ]
  }'

# Try to finish spec 1 before spec 0
PAYLOAD='{"plan_id":"'${OOO_PLAN_ID}'","spec_index":1,"status":"finished"}'
ENCODED=$(echo -n "$PAYLOAD" | base64)

curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
  -d '{
    "message": {
      "data": "'${ENCODED}'",
      "messageId": "test-msg-ooo-001"
    }
  }'

# Verify rejection
curl ${SERVICE_URL}/plans/${OOO_PLAN_ID} | jq

# Expected:
# - spec 0: still "running"
# - spec 1: still "blocked" (not finished)
# - current_spec_index = 0 (unchanged)
```

**What to verify:**
- ✅ Out-of-order update rejected
- ✅ Logs show ERROR level "Out-of-order spec finishing"
- ✅ State remains unchanged
- ✅ Response is 204 (idempotent, but logged as error)

### Test 7: Duplicate Messages (Idempotency)

Send the same message twice:

```bash
# Send first message
PAYLOAD='{"plan_id":"'${PLAN_ID}'","spec_index":0,"status":"running"}'
ENCODED=$(echo -n "$PAYLOAD" | base64)
MESSAGE_ID="test-msg-duplicate-001"

curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
  -d '{
    "message": {
      "data": "'${ENCODED}'",
      "messageId": "'${MESSAGE_ID}'"
    }
  }'

# Send the exact same message again
curl -X POST ${SERVICE_URL}/pubsub/spec-status \
  -H "Content-Type: application/json" \
  -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
  -d '{
    "message": {
      "data": "'${ENCODED}'",
      "messageId": "'${MESSAGE_ID}'"
    }
  }'

# Both should return 204 No Content
```

**What to verify:**
- ✅ Both requests return 204 No Content
- ✅ Logs show "Duplicate message detected" on second request
- ✅ State updated only once
- ✅ History contains only one entry for this message_id

## Common Troubleshooting Scenarios

### Scenario 1: Plan Not Advancing

**Symptom:** Specs stay "blocked" even after previous spec finished.

**Debugging steps:**

1. Check logs for errors:
   ```bash
   gcloud run services logs read plan-scheduler \
     --region=${REGION} \
     --log-filter='severity>=ERROR AND jsonPayload.plan_id="'${PLAN_ID}'"'
   ```

2. Verify current spec index:
   ```bash
   curl ${SERVICE_URL}/plans/${PLAN_ID} | jq '.current_spec_index'
   ```

3. Check if execution service is disabled:
   ```bash
   gcloud run services describe plan-scheduler \
     --region=${REGION} \
     --format='value(spec.template.spec.containers[0].env)' \
     | grep EXECUTION_ENABLED
   ```

4. Review Firestore state directly (if accessible)

### Scenario 2: Authentication Errors

**Symptom:** All Pub/Sub requests return 401 Unauthorized.

**Debugging steps:**

1. Verify OIDC configuration (if using OIDC):
   ```bash
   # Check audience matches actual URL
   curl ${SERVICE_URL}/health
   # Compare with PUBSUB_EXPECTED_AUDIENCE setting
   ```

2. Verify shared token (if not using OIDC):
   ```bash
   # Test with known good token
   export VERIFICATION_TOKEN=$(gcloud secrets versions access latest \
     --secret=pubsub-verification-token)
   ```

3. Check service account IAM permissions:
   ```bash
   gcloud run services get-iam-policy plan-scheduler --region=${REGION}
   ```

### Scenario 3: High Latency or Timeouts

**Symptom:** Requests take too long or time out.

**Debugging steps:**

1. Check Cloud Run instance metrics:
   ```bash
   gcloud run services describe plan-scheduler --region=${REGION}
   ```

2. Verify worker count is not too high:
   ```bash
   # Should be 1-2 for Cloud Run
   gcloud run services describe plan-scheduler \
     --region=${REGION} \
     --format='value(spec.template.spec.containers[0].env)' \
     | grep WORKERS
   ```

3. Check Firestore latency in logs

4. Increase memory if needed:
   ```bash
   gcloud run services update plan-scheduler \
     --region=${REGION} \
     --memory=1Gi
   ```

## Automated Test Script

For convenience, here's a complete bash script to run the full E2E test:

```bash
#!/bin/bash
set -e

# Configuration
SERVICE_URL=${SERVICE_URL:-http://localhost:8080}
VERIFICATION_TOKEN=${VERIFICATION_TOKEN:-test-token}

echo "=== Plan Scheduler E2E Test ==="
echo "Service URL: ${SERVICE_URL}"
echo ""

# Step 1: Health check
echo "Step 1: Checking service health..."
curl -f ${SERVICE_URL}/health > /dev/null 2>&1 || {
  echo "❌ Service is not healthy"
  exit 1
}
echo "✅ Service is healthy"
echo ""

# Step 2: Create plan
echo "Step 2: Creating test plan..."
PLAN_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
echo "Plan ID: ${PLAN_ID}"

CREATE_RESPONSE=$(curl -s -X POST ${SERVICE_URL}/plans \
  -H "Content-Type: application/json" \
  -d '{
    "id": "'${PLAN_ID}'",
    "specs": [
      {"purpose": "Spec 0", "vision": "First spec"},
      {"purpose": "Spec 1", "vision": "Second spec"},
      {"purpose": "Spec 2", "vision": "Third spec"}
    ]
  }')

echo "$CREATE_RESPONSE" | jq
echo "✅ Plan created"
echo ""

# Helper function to send status update
send_status_update() {
  local spec_index=$1
  local status=$2
  local stage=${3:-""}
  
  if [ -n "$stage" ]; then
    PAYLOAD='{"plan_id":"'${PLAN_ID}'","spec_index":'${spec_index}',"status":"'${status}'","stage":"'${stage}'"}'
  else
    PAYLOAD='{"plan_id":"'${PLAN_ID}'","spec_index":'${spec_index}',"status":"'${status}'"}'
  fi
  
  ENCODED=$(echo -n "$PAYLOAD" | base64)
  MESSAGE_ID="test-$(date +%s)-${spec_index}-${status}"
  
  curl -s -X POST ${SERVICE_URL}/pubsub/spec-status \
    -H "Content-Type: application/json" \
    -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
    -d '{
      "message": {
        "data": "'${ENCODED}'",
        "messageId": "'${MESSAGE_ID}'"
      }
    }' > /dev/null
}

# Step 3: Complete specs sequentially
echo "Step 3: Completing specs..."

for i in 0 1 2; do
  echo "  Processing spec ${i}..."
  
  # Send intermediate update
  send_status_update $i "running" "implementation"
  sleep 1
  
  # Mark as finished
  send_status_update $i "finished"
  sleep 1
  
  # Verify state
  CURRENT_STATE=$(curl -s ${SERVICE_URL}/plans/${PLAN_ID})
  COMPLETED=$(echo "$CURRENT_STATE" | jq '.completed_specs')
  echo "  ✅ Spec ${i} finished (completed: ${COMPLETED})"
done

echo ""

# Step 4: Verify final state
echo "Step 4: Verifying plan completion..."
FINAL_STATE=$(curl -s ${SERVICE_URL}/plans/${PLAN_ID})
echo "$FINAL_STATE" | jq

OVERALL_STATUS=$(echo "$FINAL_STATE" | jq -r '.overall_status')
COMPLETED_SPECS=$(echo "$FINAL_STATE" | jq '.completed_specs')
TOTAL_SPECS=$(echo "$FINAL_STATE" | jq '.total_specs')

if [ "$OVERALL_STATUS" = "finished" ] && [ "$COMPLETED_SPECS" -eq "$TOTAL_SPECS" ]; then
  echo "✅ E2E Test PASSED"
  echo "   - Plan status: ${OVERALL_STATUS}"
  echo "   - Completed specs: ${COMPLETED_SPECS}/${TOTAL_SPECS}"
  exit 0
else
  echo "❌ E2E Test FAILED"
  echo "   - Plan status: ${OVERALL_STATUS} (expected: finished)"
  echo "   - Completed specs: ${COMPLETED_SPECS}/${TOTAL_SPECS}"
  exit 1
fi
```

Save this as `test-e2e.sh`, make it executable, and run:

```bash
chmod +x test-e2e.sh
export SERVICE_URL=http://localhost:8080
export VERIFICATION_TOKEN=your-token
./test-e2e.sh
```

## Related Documentation

- [Cloud Run Deployment Guide](./cloud-run.md) - Deployment instructions
- [Main README](../README.md) - General service documentation
- [API Endpoints Reference](../README.md#api-endpoints) - Complete API documentation

## Summary

This guide covered:

✅ Complete end-to-end testing workflow  
✅ Simulating Pub/Sub push payloads manually  
✅ Monitoring logs and observing state transitions  
✅ Verifying plan completion  
✅ Testing failure modes and error handling  
✅ Common troubleshooting scenarios  
✅ Automated test script for CI/CD

Use these procedures to validate deployments, troubleshoot issues, and ensure the service operates correctly before production use.
