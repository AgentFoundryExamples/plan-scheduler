# Cloud Run Deployment Guide

This guide provides step-by-step instructions for deploying the Plan Scheduler service to Google Cloud Run, including environment configuration, Pub/Sub integration, and operational best practices.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Building and Pushing the Container](#building-and-pushing-the-container)
- [Deploying to Cloud Run](#deploying-to-cloud-run)
- [Pub/Sub Push Subscription Configuration](#pubsub-push-subscription-configuration)
- [Authentication Methods](#authentication-methods)
- [Recommended Cloud Run Settings](#recommended-cloud-run-settings)
- [Security Best Practices](#security-best-practices)
- [Monitoring and Logging](#monitoring-and-logging)
- [Troubleshooting](#troubleshooting)

## Prerequisites

Before deploying to Cloud Run, ensure you have:

- Google Cloud Project with billing enabled
- `gcloud` CLI installed and authenticated
- Docker installed (for local builds)
- Appropriate IAM permissions:
  - `roles/run.admin` - Deploy Cloud Run services
  - `roles/iam.serviceAccountUser` - Use service accounts
  - `roles/storage.admin` - Push to Container Registry
  - `roles/pubsub.admin` - Configure Pub/Sub subscriptions
  - `roles/datastore.user` - Access Firestore

## Environment Variables

The Plan Scheduler service is configured entirely through environment variables. Below is a comprehensive reference of all configuration options.

### Required Environment Variables

These variables are essential for production deployments:

| Variable | Description | Example | Required When |
|----------|-------------|---------|---------------|
| `FIRESTORE_PROJECT_ID` | GCP project ID for Firestore operations | `my-project-123` | Always (for Firestore access) |
| `PUBSUB_VERIFICATION_TOKEN` | Shared secret for Pub/Sub authentication | `J7ZigtqyXkbATeElXULwz...` | `PUBSUB_OIDC_ENABLED=false` |
| `PUBSUB_EXPECTED_AUDIENCE` | Expected JWT audience claim (Cloud Run URL) | `https://plan-scheduler-abc123.run.app` | `PUBSUB_OIDC_ENABLED=true` |

### Optional Environment Variables

These variables have sensible defaults but can be customized:

| Variable | Default | Description | Valid Values |
|----------|---------|-------------|--------------|
| `PORT` | `8080` | HTTP port for the service | `1-65535` |
| `SERVICE_NAME` | `plan-scheduler` | Service identifier for logging | Any string |
| `LOG_LEVEL` | `INFO` | Application logging level | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `WORKERS` | `1` | Number of uvicorn workers | `1-16` (recommend `1-2` for Cloud Run) |
| `GOOGLE_APPLICATION_CREDENTIALS` | `""` | Path to service account key file | File path (not needed on Cloud Run) |

### Authentication Configuration

The service supports two authentication methods for Pub/Sub push requests:

#### OIDC Authentication (Recommended for Production)

| Variable | Default | Description |
|----------|---------|-------------|
| `PUBSUB_OIDC_ENABLED` | `true` | Enable OIDC JWT token verification |
| `PUBSUB_EXPECTED_AUDIENCE` | `""` | Expected audience claim (your Cloud Run URL) |
| `PUBSUB_EXPECTED_ISSUER` | `https://accounts.google.com` | Expected issuer claim |
| `PUBSUB_SERVICE_ACCOUNT_EMAIL` | `""` | Expected service account email (optional but recommended) |

#### Shared Token Authentication (Fallback/Legacy)

| Variable | Default | Description |
|----------|---------|-------------|
| `PUBSUB_VERIFICATION_TOKEN` | `""` | Shared secret sent in `x-goog-pubsub-verification-token` header |

### Execution Service Configuration

Control external execution service integration:

| Variable | Default | Description |
|----------|---------|-------------|
| `EXECUTION_ENABLED` | `true` | Enable/disable execution service triggers |
| `EXECUTION_API_URL` | `""` | Base URL for external execution API (future use) |
| `EXECUTION_API_KEY` | `""` | API key for external execution service (future use) |

### Environment Variable Configuration Examples

**Minimal Production Configuration (OIDC):**
```bash
FIRESTORE_PROJECT_ID=${PROJECT_ID}
PUBSUB_OIDC_ENABLED=true
PUBSUB_EXPECTED_AUDIENCE=${SERVICE_URL}
PUBSUB_SERVICE_ACCOUNT_EMAIL=${PUBSUB_SERVICE_ACCOUNT_EMAIL}
```

**Minimal Production Configuration (Shared Token):**
```bash
FIRESTORE_PROJECT_ID=${PROJECT_ID}
PUBSUB_OIDC_ENABLED=false
PUBSUB_VERIFICATION_TOKEN=${PUBSUB_VERIFICATION_TOKEN}
```

**Development/Testing Configuration:**
```bash
FIRESTORE_PROJECT_ID=${DEV_PROJECT_ID}
LOG_LEVEL=DEBUG
EXECUTION_ENABLED=false
PUBSUB_OIDC_ENABLED=false
PUBSUB_VERIFICATION_TOKEN=${DEV_TOKEN}
```

### Using .env Files

For local development, create a `.env` file from the provided template:

```bash
# Copy the example file
cp .env.example .env

# Edit with your configuration
nano .env  # or your preferred editor
```

The `.env.example` file in the repository root contains all available variables with descriptions and example values.

## Building and Pushing the Container

### Option 1: Cloud Build (Recommended)

Build the container image directly in Google Cloud:

```bash
# Set your project ID
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1

# Build and push using Cloud Build
gcloud builds submit --tag gcr.io/${PROJECT_ID}/plan-scheduler:latest

# Optional: Tag with version
gcloud builds submit --tag gcr.io/${PROJECT_ID}/plan-scheduler:v1.0.0
```

### Option 2: Local Build and Push

Build locally and push to Google Container Registry:

```bash
# Configure Docker authentication
gcloud auth configure-docker

# Build the image
docker build -t gcr.io/${PROJECT_ID}/plan-scheduler:latest .

# Optional: Build with custom UID/GID
docker build \
  --build-arg APP_UID=10000 \
  --build-arg APP_GID=10000 \
  -t gcr.io/${PROJECT_ID}/plan-scheduler:latest .

# Push to GCR
docker push gcr.io/${PROJECT_ID}/plan-scheduler:latest
```

## Deploying to Cloud Run

### Basic Deployment

Deploy the service with minimal configuration:

```bash
gcloud run deploy plan-scheduler \
  --image gcr.io/${PROJECT_ID}/plan-scheduler:latest \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars FIRESTORE_PROJECT_ID=${PROJECT_ID} \
  --set-env-vars PUBSUB_VERIFICATION_TOKEN=your-secure-token
```

### Production Deployment with OIDC (Recommended)

Deploy with OIDC authentication for enhanced security:

```bash
# First deployment to get the service URL
gcloud run deploy plan-scheduler \
  --image gcr.io/${PROJECT_ID}/plan-scheduler:latest \
  --region ${REGION} \
  --platform managed \
  --no-allow-unauthenticated \
  --set-env-vars FIRESTORE_PROJECT_ID=${PROJECT_ID} \
  --set-env-vars SERVICE_NAME=plan-scheduler \
  --set-env-vars WORKERS=1 \
  --set-env-vars LOG_LEVEL=INFO \
  --set-env-vars PUBSUB_OIDC_ENABLED=true \
  --set-env-vars PUBSUB_EXPECTED_ISSUER=https://accounts.google.com \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --timeout 60s \
  --concurrency 80

# Get the service URL
SERVICE_URL=$(gcloud run services describe plan-scheduler \
  --region ${REGION} \
  --format 'value(status.url)')

echo "Service URL: ${SERVICE_URL}"

# Update with the actual service URL as the OIDC audience
gcloud run services update plan-scheduler \
  --region ${REGION} \
  --set-env-vars PUBSUB_EXPECTED_AUDIENCE=${SERVICE_URL}
```

### Using Secret Manager for Sensitive Values

Store sensitive configuration in Secret Manager:

```bash
# Create a secret for the verification token
echo -n "your-secure-random-token" | gcloud secrets create pubsub-verification-token \
  --data-file=- \
  --replication-policy=automatic

# Deploy with secret
gcloud run deploy plan-scheduler \
  --image gcr.io/${PROJECT_ID}/plan-scheduler:latest \
  --region ${REGION} \
  --platform managed \
  --set-env-vars FIRESTORE_PROJECT_ID=${PROJECT_ID} \
  --set-secrets PUBSUB_VERIFICATION_TOKEN=pubsub-verification-token:latest
```

### Granting Firestore Access

Grant the Cloud Run service account permission to access Firestore:

```bash
# Get the service account
SERVICE_ACCOUNT=$(gcloud run services describe plan-scheduler \
  --region ${REGION} \
  --format 'value(spec.template.spec.serviceAccountName)')

# Grant Firestore access
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/datastore.user"
```

## Pub/Sub Push Subscription Configuration

The service receives spec status updates via Pub/Sub push notifications to the `/pubsub/spec-status` endpoint.

### Step 1: Create Pub/Sub Topic

```bash
# Create the topic for spec status updates
gcloud pubsub topics create spec-status-updates \
  --project ${PROJECT_ID}
```

### Step 2: Create Service Account for Pub/Sub (OIDC Method)

For OIDC authentication, create a dedicated service account:

```bash
# Create service account
gcloud iam service-accounts create pubsub-invoker \
  --display-name="Pub/Sub Invoker for Plan Scheduler" \
  --project ${PROJECT_ID}

# Grant permission to invoke Cloud Run
gcloud run services add-iam-policy-binding plan-scheduler \
  --region=${REGION} \
  --member="serviceAccount:pubsub-invoker@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.invoker" \
  --project ${PROJECT_ID}
```

### Step 3: Create Push Subscription

#### Option A: OIDC Authentication (Recommended)

```bash
# Get the service URL
SERVICE_URL=$(gcloud run services describe plan-scheduler \
  --region ${REGION} \
  --format 'value(status.url)')

# Create push subscription with OIDC
gcloud pubsub subscriptions create spec-status-push \
  --topic=spec-status-updates \
  --push-endpoint=${SERVICE_URL}/pubsub/spec-status \
  --push-auth-service-account=pubsub-invoker@${PROJECT_ID}.iam.gserviceaccount.com \
  --ack-deadline=60 \
  --min-retry-delay=10s \
  --max-retry-delay=600s \
  --project ${PROJECT_ID}
```

#### Option B: Shared Token Authentication

```bash
# Generate a secure token
TOKEN=$(openssl rand -base64 32)

# Store in Secret Manager
echo -n "$TOKEN" | gcloud secrets create pubsub-verification-token \
  --data-file=- \
  --replication-policy=automatic \
  --project ${PROJECT_ID}

# Create push subscription with token
gcloud pubsub subscriptions create spec-status-push \
  --topic=spec-status-updates \
  --push-endpoint=${SERVICE_URL}/pubsub/spec-status \
  --push-auth-token-header="x-goog-pubsub-verification-token=$TOKEN" \
  --ack-deadline=60 \
  --min-retry-delay=10s \
  --max-retry-delay=600s \
  --project ${PROJECT_ID}
```

### Step 4: Configure Dead-Letter Topic (Optional but Recommended)

Handle messages that fail repeatedly:

```bash
# Create dead-letter topic
gcloud pubsub topics create spec-status-dlq \
  --project ${PROJECT_ID}

# Update subscription with dead-letter configuration
gcloud pubsub subscriptions update spec-status-push \
  --dead-letter-topic=spec-status-dlq \
  --max-delivery-attempts=5 \
  --project ${PROJECT_ID}

# Grant Pub/Sub permissions to publish to DLQ
gcloud pubsub topics add-iam-policy-binding spec-status-dlq \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/pubsub.publisher" \
  --project ${PROJECT_ID}

# Grant Pub/Sub permissions to subscribe to DLQ
gcloud pubsub subscriptions add-iam-policy-binding spec-status-push \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber" \
  --project ${PROJECT_ID}
```

### Testing the Pub/Sub Integration

```bash
# Publish a test message
PAYLOAD='{"plan_id":"550e8400-e29b-41d4-a716-446655440000","spec_index":0,"status":"running","stage":"testing"}'
gcloud pubsub topics publish spec-status-updates \
  --message="$PAYLOAD" \
  --project ${PROJECT_ID}

# Monitor Cloud Run logs
gcloud run services logs read plan-scheduler \
  --region=${REGION} \
  --limit=20 \
  --project ${PROJECT_ID}

# Check subscription status
gcloud pubsub subscriptions describe spec-status-push \
  --project ${PROJECT_ID}
```

## Authentication Methods

### OIDC JWT Authentication (Recommended)

OIDC provides the most secure authentication method without managing shared secrets.

**How it works:**
1. Pub/Sub sends JWT token in `Authorization: Bearer <token>` header
2. Service validates JWT signature using Google's public keys
3. Service verifies audience, issuer, and service account email claims
4. Cloud Run automatically handles token verification at the infrastructure level

**Configuration:**
```bash
# Deploy with OIDC enabled
gcloud run services update plan-scheduler \
  --region ${REGION} \
  --set-env-vars PUBSUB_OIDC_ENABLED=true \
  --set-env-vars PUBSUB_EXPECTED_AUDIENCE=${SERVICE_URL} \
  --set-env-vars PUBSUB_SERVICE_ACCOUNT_EMAIL=pubsub-invoker@${PROJECT_ID}.iam.gserviceaccount.com
```

**Benefits:**
- No shared secrets to manage or rotate
- Automatic token verification by Cloud Run
- Service account identity in JWT claims
- Integrated with Cloud IAM

### Shared Token Authentication (Fallback)

Shared token authentication uses a static secret sent in the request header.

**How it works:**
1. Pub/Sub sends token in `x-goog-pubsub-verification-token` header
2. Service compares token with configured `PUBSUB_VERIFICATION_TOKEN`
3. Request proceeds if tokens match

**Configuration:**
```bash
# Deploy with shared token
gcloud run services update plan-scheduler \
  --region ${REGION} \
  --set-env-vars PUBSUB_OIDC_ENABLED=false \
  --set-secrets PUBSUB_VERIFICATION_TOKEN=pubsub-verification-token:latest
```

**When to use:**
- Legacy integrations requiring shared secrets
- Non-Cloud Run environments without OIDC support
- As a fallback when OIDC validation fails

## Recommended Cloud Run Settings

### Resource Allocation

| Setting | Recommended Value | Description |
|---------|------------------|-------------|
| **Memory** | `512Mi` - `1Gi` | Sufficient for typical workloads; increase if processing large plans |
| **CPU** | `1` (1 vCPU) | Adequate for orchestration workload |
| **Timeout** | `60s` - `300s` | Request timeout; 60s sufficient for most operations |

### Scaling Configuration

| Setting | Recommended Value | Description |
|---------|------------------|-------------|
| **Min Instances** | `0` - `1` | Use `0` for cost savings; use `1` to eliminate cold starts |
| **Max Instances** | `10` - `100` | Limit based on expected concurrency and Firestore quotas |
| **Concurrency** | `80` - `100` | Max concurrent requests per instance |

### Deployment Settings

| Setting | Recommended Value | Description |
|---------|------------------|-------------|
| **Workers** | `1` - `2` | Uvicorn workers; Cloud Run scales via instances, not workers |
| **Execution Environment** | `gen2` | Use second-generation execution environment |

### Example Configuration

```bash
gcloud run deploy plan-scheduler \
  --image gcr.io/${PROJECT_ID}/plan-scheduler:latest \
  --region ${REGION} \
  --platform managed \
  --memory 512Mi \
  --cpu 1 \
  --timeout 60s \
  --min-instances 0 \
  --max-instances 10 \
  --concurrency 80 \
  --execution-environment gen2 \
  --set-env-vars WORKERS=1
```

### Scaling Considerations

**Cold Starts:**
- **Min Instances = 0**: Cost-effective but may have cold start latency (~1-3 seconds)
- **Min Instances = 1**: Eliminates cold starts but incurs constant cost

**Concurrency:**
- Higher concurrency = fewer instances needed = lower cost
- Monitor CPU and memory usage to ensure instances aren't overloaded
- The service is async-capable, so concurrency of 80-100 is safe

**Workers:**
- Cloud Run scales horizontally (more instances), not vertically (more workers per instance)
- Use `WORKERS=1` or `WORKERS=2` to keep memory usage low
- Each worker adds ~50-100 MB memory overhead

## Security Best Practices

### Token Rotation (Shared Token Method)

Rotate verification tokens regularly without downtime:

```bash
# Step 1: Generate new token
NEW_TOKEN=$(openssl rand -base64 32)

# Step 2: Create new secret version
echo -n "$NEW_TOKEN" | gcloud secrets versions add pubsub-verification-token \
  --data-file=- \
  --project ${PROJECT_ID}

# Step 3: Update Cloud Run service (new instances use new token)
gcloud run services update plan-scheduler \
  --region ${REGION} \
  --update-secrets PUBSUB_VERIFICATION_TOKEN=pubsub-verification-token:latest \
  --project ${PROJECT_ID}

# Step 4: Wait for all instances to restart and verify rollout completion
echo "Waiting for service rollout to complete..."
gcloud run services describe plan-scheduler \
  --region ${REGION} \
  --format='get(status.conditions)' \
  --project ${PROJECT_ID}

# Poll until rollout is complete (check every 10 seconds, max 3 minutes)
for i in {1..18}; do
  READY=$(gcloud run services describe plan-scheduler \
    --region ${REGION} \
    --format='value(status.conditions.status)' \
    --project ${PROJECT_ID} 2>/dev/null || echo "Unknown")
  
  if [[ "$READY" == *"True"* ]]; then
    echo "✅ Service rollout complete"
    break
  fi
  
  if [ $i -eq 18 ]; then
    echo "⚠️  Timeout waiting for rollout. Check service status manually."
    exit 1
  fi
  
  echo "Waiting for instances to restart... ($((i * 10))s)"
  sleep 10
done

# Step 5: Update Pub/Sub subscription
gcloud pubsub subscriptions update spec-status-push \
  --push-auth-token-header="x-goog-pubsub-verification-token=$NEW_TOKEN" \
  --project ${PROJECT_ID}

# Step 6: Verify token rotation by checking logs for successful authentication
echo "Verifying new token is working..."
gcloud run services logs read plan-scheduler \
  --region=${REGION} \
  --limit=10 \
  --project ${PROJECT_ID} \
  | grep -i "authenticated" || echo "⚠️  No authentication logs found yet. Check again in a few moments."

echo "✅ Token rotation complete"
```

**Important**: The old token remains valid in any running instances until they restart. The script above waits for Cloud Run to complete the rollout before updating the Pub/Sub subscription, ensuring zero downtime.

### Service Account Best Practices

1. **Use dedicated service accounts** for different components:
   - One for Cloud Run (Firestore access)
   - One for Pub/Sub push (Cloud Run invocation)

2. **Principle of least privilege:**
   ```bash
   # Cloud Run service account - only needs Firestore access
   gcloud projects add-iam-policy-binding ${PROJECT_ID} \
     --member="serviceAccount:plan-scheduler-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
     --role="roles/datastore.user"
   
   # Pub/Sub service account - only needs Cloud Run invoke
   gcloud run services add-iam-policy-binding plan-scheduler \
     --region=${REGION} \
     --member="serviceAccount:pubsub-invoker@${PROJECT_ID}.iam.gserviceaccount.com" \
     --role="roles/run.invoker"
   ```

3. **Never commit secrets** to source control - always use Secret Manager

### Network Security

1. **Require authentication** for sensitive endpoints:
   ```bash
   gcloud run services update plan-scheduler \
     --region ${REGION} \
     --no-allow-unauthenticated
   ```

2. **Use VPC Connector** for private network access (optional):
   ```bash
   gcloud run services update plan-scheduler \
     --region ${REGION} \
     --vpc-connector=your-connector \
     --vpc-egress=private-ranges-only
   ```

### Secret Management

Store all sensitive values in Secret Manager:

```bash
# Create secrets
echo -n "token-value" | gcloud secrets create pubsub-verification-token --data-file=-
echo -n "api-key" | gcloud secrets create execution-api-key --data-file=-

# Deploy with secrets
gcloud run services update plan-scheduler \
  --region ${REGION} \
  --set-secrets PUBSUB_VERIFICATION_TOKEN=pubsub-verification-token:latest \
  --set-secrets EXECUTION_API_KEY=execution-api-key:latest
```

## Monitoring and Logging

### Viewing Logs

```bash
# View recent logs
gcloud run services logs read plan-scheduler \
  --region=${REGION} \
  --limit=50

# Stream logs in real-time
gcloud run services logs tail plan-scheduler \
  --region=${REGION}

# Filter logs by severity
gcloud run services logs read plan-scheduler \
  --region=${REGION} \
  --log-filter='severity>=ERROR'

# Filter logs by plan_id
gcloud run services logs read plan-scheduler \
  --region=${REGION} \
  --log-filter='jsonPayload.plan_id="550e8400-e29b-41d4-a716-446655440000"'
```

### Important Log Events

The service emits structured JSON logs with the following key events:

| Event Type | Log Level | Description |
|------------|-----------|-------------|
| `terminal_spec_finished` | INFO | Spec completed successfully |
| `terminal_plan_finished` | INFO | All specs completed |
| `terminal_spec_failed` | ERROR | Spec execution failed |
| `non_terminal_update` | INFO | Intermediate status update |
| Authentication success | INFO | Request authenticated successfully |
| Authentication failure | WARNING | Invalid or missing credentials |
| Out-of-order events | ERROR | Spec finished out of sequence |

### Secure Logging Practices

The service implements secure logging practices to protect sensitive data:

- **Never logs sensitive data**: Tokens, credentials, and personal information are excluded from logs
- **Automatic payload sanitization**: Raw payloads are truncated to prevent log bloat and data exposure
- **Structured JSON format**: Facilitates parsing, filtering, and security analysis
- **Authentication failures logged**: Monitor for potential security issues
- **Log retention**: Configure retention policies to comply with data retention requirements

For complete logging documentation, see the [main README - Secure Logging Practices](../README.md#pubsub-webhook).

### Health Endpoints

The service provides health check endpoints:

```bash
# Check service health
curl ${SERVICE_URL}/health

# Expected response: {"status":"ok"}
```

Cloud Run automatically monitors the container health and restarts unhealthy instances.

### Monitoring Metrics

Key metrics to monitor in Cloud Logging:

1. **Request Rate**: Requests per second to `/pubsub/spec-status`
2. **Error Rate**: HTTP 4xx and 5xx responses
3. **Request Latency**: P50, P95, P99 latency
4. **Instance Count**: Number of active Cloud Run instances
5. **Cold Start Frequency**: How often new instances are created

### Setting Up Alerts

Create alerting policies for critical events:

```bash
# Example: Alert on error rate > 5%
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="Plan Scheduler Error Rate" \
  --condition-display-name="Error rate > 5%" \
  --condition-threshold-value=5 \
  --condition-threshold-duration=300s
```

## Troubleshooting

### Common Issues

#### Authentication Failures

**Symptom:** 401 Unauthorized responses, logs show "Invalid or missing authentication"

**Solutions:**
1. Verify OIDC configuration:
   ```bash
   gcloud run services describe plan-scheduler \
     --region=${REGION} \
     --format='value(spec.template.spec.containers[0].env)'
   ```
   Check that `PUBSUB_EXPECTED_AUDIENCE` matches actual service URL.

2. Verify service account has `roles/run.invoker`:
   ```bash
   gcloud run services get-iam-policy plan-scheduler \
     --region=${REGION}
   ```

3. Check token configuration (shared token method):
   ```bash
   gcloud secrets versions access latest --secret=pubsub-verification-token
   ```

#### Firestore Access Errors

**Symptom:** Logs show "Permission denied" for Firestore operations

**Solutions:**
1. Grant Firestore access to service account:
   ```bash
   SERVICE_ACCOUNT=$(gcloud run services describe plan-scheduler \
     --region=${REGION} \
     --format='value(spec.template.spec.serviceAccountName)')
   
   gcloud projects add-iam-policy-binding ${PROJECT_ID} \
     --member="serviceAccount:${SERVICE_ACCOUNT}" \
     --role="roles/datastore.user"
   ```

2. Verify project ID is correct:
   ```bash
   gcloud run services describe plan-scheduler \
     --region=${REGION} \
     --format='value(spec.template.spec.containers[0].env)' \
     | grep FIRESTORE_PROJECT_ID
   ```

#### Out-of-Order Spec Events

**Symptom:** Logs show "Out-of-order spec finishing detected"

**Causes:**
- Multiple execution services running concurrently
- Execution service not respecting sequential spec order
- Race conditions in external systems

**Solutions:**
1. Review history in Firestore to understand sequence of events
2. Check if multiple execution instances are triggering for same plan
3. Verify execution orchestration logic

#### Cold Start Latency

**Symptom:** First request after idle period is slow (~1-3 seconds)

**Solutions:**
1. Set min instances to 1 to keep one instance warm:
   ```bash
   gcloud run services update plan-scheduler \
     --region=${REGION} \
     --min-instances=1
   ```

2. Use Cloud Scheduler to send periodic health checks:
   ```bash
   gcloud scheduler jobs create http keep-warm \
     --schedule="*/5 * * * *" \
     --uri="${SERVICE_URL}/health" \
     --http-method=GET
   ```

#### Memory or CPU Issues

**Symptom:** Instances restarting frequently, high latency

**Solutions:**
1. Increase memory allocation:
   ```bash
   gcloud run services update plan-scheduler \
     --region=${REGION} \
     --memory=1Gi
   ```

2. Reduce concurrency per instance:
   ```bash
   gcloud run services update plan-scheduler \
     --region=${REGION} \
     --concurrency=50
   ```

3. Check worker count is not too high:
   ```bash
   gcloud run services update plan-scheduler \
     --region=${REGION} \
     --set-env-vars WORKERS=1
   ```

### Debugging Commands

```bash
# Get full service description
gcloud run services describe plan-scheduler \
  --region=${REGION} \
  --format=yaml

# View recent revisions
gcloud run revisions list \
  --service=plan-scheduler \
  --region=${REGION}

# View environment variables
gcloud run services describe plan-scheduler \
  --region=${REGION} \
  --format='value(spec.template.spec.containers[0].env)'

# Check IAM policy
gcloud run services get-iam-policy plan-scheduler \
  --region=${REGION}

# Test connectivity from inside Cloud Run
gcloud run services update plan-scheduler \
  --region=${REGION} \
  --set-env-vars DEBUG_MODE=true
```

### Getting Help

If issues persist:

1. **Check service logs** with increased verbosity:
   ```bash
   gcloud run services update plan-scheduler \
     --region=${REGION} \
     --set-env-vars LOG_LEVEL=DEBUG
   ```

2. **Review Firestore documents** for plan and spec state

3. **Verify Pub/Sub subscription** is delivering messages:
   ```bash
   gcloud pubsub subscriptions describe spec-status-push
   ```

4. **Check Cloud Run quotas** in the GCP Console

## Multi-Region Considerations

For future multi-region deployments, consider:

1. **Firestore Multi-Region**: Configure Firestore in multi-region mode
2. **Global Load Balancer**: Use Cloud Load Balancing for geographic distribution
3. **Regional Pub/Sub**: Create regional topics and subscriptions
4. **State Consistency**: Ensure Firestore transactions handle multi-region writes correctly

Currently, the service is designed for single-region deployments. Multi-region support requires additional consideration for distributed transactions and eventual consistency.

## Related Documentation

- [Manual End-to-End Testing Guide](./manual-e2e.md) - Step-by-step testing procedures
- [Main README](../README.md) - General service documentation
- [API Endpoints Reference](../README.md#api-endpoints) - Complete API documentation
- [Environment Variables Reference](../README.md#environment-variables) - Full variable reference

## Placeholders

Throughout this guide, replace the following placeholders with your actual values:

- `${PROJECT_ID}` - Your Google Cloud project ID
- `${REGION}` - Your desired Cloud Run region (e.g., `us-central1`)
- `${SERVICE_URL}` - Your Cloud Run service URL
- `${PROJECT_NUMBER}` - Your GCP project number (find in Console or via `gcloud projects describe ${PROJECT_ID}`)
- `${PUBSUB_SERVICE_ACCOUNT_EMAIL}` - Email of the Pub/Sub service account (e.g., `pubsub-invoker@${PROJECT_ID}.iam.gserviceaccount.com`)
- `${PUBSUB_VERIFICATION_TOKEN}` - Generate with `openssl rand -base64 32` and store in Secret Manager
- `${DEV_PROJECT_ID}` - Development/testing project ID
- `${DEV_TOKEN}` - Development/testing token (generate with `openssl rand -base64 32`)

**Security Note**: Never commit hardcoded tokens or credentials. Always use placeholders in documentation and Secret Manager for actual deployments.

All example commands avoid hardcoding specific project values to ensure they work across different environments.
