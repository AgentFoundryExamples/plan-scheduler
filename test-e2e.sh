#!/bin/bash
set -euo pipefail

# Plan Scheduler End-to-End Test Script
# This script tests the complete workflow: create plan, send status updates, verify completion
#
# Usage:
#   export SERVICE_URL=http://localhost:8080
#   export VERIFICATION_TOKEN=your-token
#   ./test-e2e.sh
#
# Exit codes:
#   0 - Test passed
#   1 - Test failed or error occurred

# Configuration
SERVICE_URL=${SERVICE_URL:-http://localhost:8080}
VERIFICATION_TOKEN=${VERIFICATION_TOKEN:-test-token}

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=== Plan Scheduler E2E Test ==="
echo "Service URL: ${SERVICE_URL}"
echo ""

# Helper function to check if jq is available
check_jq() {
  if ! command -v jq &> /dev/null; then
    echo -e "${RED}❌ Error: jq is required but not installed${NC}"
    echo "Install jq: https://stedolan.github.io/jq/download/"
    exit 1
  fi
}

# Helper function to validate HTTP response
validate_response() {
  local response=$1
  local expected_status=$2
  local context=$3
  
  local http_status=$(echo "$response" | tail -n1)
  local body=$(echo "$response" | sed '$d')
  
  if [ "$http_status" != "$expected_status" ]; then
    echo -e "${RED}❌ Error in ${context}: Expected HTTP ${expected_status}, got ${http_status}${NC}"
    echo "Response body: $body"
    return 1
  fi
  
  echo "$body"
}

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
  
  local response=$(curl -w "\n%{http_code}" -s -X POST ${SERVICE_URL}/pubsub/spec-status \
    -H "Content-Type: application/json" \
    -H "x-goog-pubsub-verification-token: ${VERIFICATION_TOKEN}" \
    -d '{
      "message": {
        "data": "'${ENCODED}'",
        "messageId": "'${MESSAGE_ID}'"
      }
    }')
  
  validate_response "$response" "204" "status update for spec ${spec_index}" > /dev/null
}

# Check prerequisites
check_jq

# Step 1: Health check
echo "Step 1: Checking service health..."
health_response=$(curl -w "\n%{http_code}" -sf ${SERVICE_URL}/health 2>&1 || echo -e "\n000")
health_status=$(echo "$health_response" | tail -n1)

if [ "$health_status" != "200" ]; then
  echo -e "${RED}❌ Service is not healthy (HTTP ${health_status})${NC}"
  echo "Make sure the service is running at ${SERVICE_URL}"
  exit 1
fi
echo -e "${GREEN}✅ Service is healthy${NC}"
echo ""

# Step 2: Create plan
echo "Step 2: Creating test plan..."
PLAN_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
echo "Plan ID: ${PLAN_ID}"

create_response=$(curl -w "\n%{http_code}" -s -X POST ${SERVICE_URL}/plans \
  -H "Content-Type: application/json" \
  -d '{
    "id": "'${PLAN_ID}'",
    "specs": [
      {"purpose": "Spec 0", "vision": "First spec"},
      {"purpose": "Spec 1", "vision": "Second spec"},
      {"purpose": "Spec 2", "vision": "Third spec"}
    ]
  }')

create_body=$(validate_response "$create_response" "201" "plan creation")
if [ $? -ne 0 ]; then
  exit 1
fi

echo "$create_body" | jq '.'
echo -e "${GREEN}✅ Plan created${NC}"
echo ""

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
  state_response=$(curl -w "\n%{http_code}" -s ${SERVICE_URL}/plans/${PLAN_ID})
  state_body=$(validate_response "$state_response" "200" "plan status query")
  
  if [ $? -ne 0 ]; then
    exit 1
  fi
  
  COMPLETED=$(echo "$state_body" | jq '.completed_specs')
  
  if [ -z "$COMPLETED" ] || [ "$COMPLETED" = "null" ]; then
    echo -e "${RED}❌ Failed to parse completed_specs from response${NC}"
    exit 1
  fi
  
  echo -e "  ${GREEN}✅ Spec ${i} finished (completed: ${COMPLETED})${NC}"
done

echo ""

# Step 4: Verify final state
echo "Step 4: Verifying plan completion..."
final_response=$(curl -w "\n%{http_code}" -s ${SERVICE_URL}/plans/${PLAN_ID})
final_body=$(validate_response "$final_response" "200" "final plan status")

if [ $? -ne 0 ]; then
  exit 1
fi

echo "$final_body" | jq '.'

OVERALL_STATUS=$(echo "$final_body" | jq -r '.overall_status')
COMPLETED_SPECS=$(echo "$final_body" | jq '.completed_specs')
TOTAL_SPECS=$(echo "$final_body" | jq '.total_specs')

# Validate parsed values
if [ -z "$OVERALL_STATUS" ] || [ "$OVERALL_STATUS" = "null" ]; then
  echo -e "${RED}❌ Failed to parse overall_status from response${NC}"
  exit 1
fi

if [ -z "$COMPLETED_SPECS" ] || [ "$COMPLETED_SPECS" = "null" ]; then
  echo -e "${RED}❌ Failed to parse completed_specs from response${NC}"
  exit 1
fi

if [ -z "$TOTAL_SPECS" ] || [ "$TOTAL_SPECS" = "null" ]; then
  echo -e "${RED}❌ Failed to parse total_specs from response${NC}"
  exit 1
fi

# Final validation
if [ "$OVERALL_STATUS" = "finished" ] && [ "$COMPLETED_SPECS" -eq "$TOTAL_SPECS" ]; then
  echo ""
  echo -e "${GREEN}✅ E2E Test PASSED${NC}"
  echo "   - Plan status: ${OVERALL_STATUS}"
  echo "   - Completed specs: ${COMPLETED_SPECS}/${TOTAL_SPECS}"
  exit 0
else
  echo ""
  echo -e "${RED}❌ E2E Test FAILED${NC}"
  echo "   - Plan status: ${OVERALL_STATUS} (expected: finished)"
  echo "   - Completed specs: ${COMPLETED_SPECS}/${TOTAL_SPECS}"
  exit 1
fi
