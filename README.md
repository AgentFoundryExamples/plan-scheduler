# Plan Scheduler Service

FastAPI service for plan scheduling with Firestore integration and Pub/Sub support.

## Features

- FastAPI web framework with automatic OpenAPI documentation
- JSON-structured logging for production observability
- Environment-based configuration with sensible defaults
- Health check endpoint for monitoring
- Firestore integration with credential-aware initialization
- Poetry for dependency management
- Comprehensive test coverage

## Prerequisites

- Python 3.12 or higher
- Poetry (for dependency management)
- GCP service account credentials (for Firestore/Pub/Sub access)

## Local Development Setup

### 1. Install Dependencies

```bash
# Install Poetry if not already installed
pip install poetry

# Install project dependencies
poetry install
```

### 2. Configure Environment Variables

Copy the example environment file and update with your values:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

- `FIRESTORE_PROJECT_ID`: Your GCP project ID (required for Firestore)
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to your service account JSON key file
- `PORT`: Port to run the service (default: 8080)
- `SERVICE_NAME`: Service identifier for logging (default: plan-scheduler)
- `PUBSUB_VERIFICATION_TOKEN`: Token for Pub/Sub request verification

#### Setting up Google Cloud Authentication

The service uses **Application Default Credentials (ADC)** to authenticate with Firestore. Choose one of these methods:

**Option 1: Service Account Key (Recommended for production)**

1. Create a service account in GCP Console
2. Grant the service account the `Cloud Datastore User` role (or `Firestore Service Agent` for broader access)
3. Download the JSON key file
4. Set the path in your `.env` file:
   ```
   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
   ```

**Option 2: User Credentials (Local development only)**

```bash
gcloud auth application-default login
```

This creates credentials that your application can use locally without needing a service account key file.

#### Required Firestore Permissions

Your service account or user credentials need these permissions:
- `datastore.entities.create` - Create documents
- `datastore.entities.get` - Read documents
- `datastore.entities.delete` - Delete documents

These are included in the `Cloud Datastore User` role.

### 3. Run the Service

```bash
# Using Poetry
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# Or activate the virtual environment first
poetry shell
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

The service will be available at:
- Main API: http://localhost:8080
- Health check: http://localhost:8080/health
- API documentation (Swagger UI): http://localhost:8080/docs
- API documentation (ReDoc): http://localhost:8080/redoc
- OpenAPI schema: http://localhost:8080/openapi.json

### 4. Run Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=app --cov-report=term-missing

# Run specific test file
poetry run pytest tests/test_health.py

# Run with verbose output
poetry run pytest -v
```

## Environment Variables

All environment variables have sensible defaults and will emit warnings if critical values are missing:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `FIRESTORE_PROJECT_ID` | GCP project ID for Firestore | `""` | Recommended |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service account JSON | `""` | Recommended |
| `PORT` | Service port (1-65535) | `8080` | No |
| `SERVICE_NAME` | Service name for logging | `plan-scheduler` | No |
| `PUBSUB_VERIFICATION_TOKEN` | Pub/Sub verification token | `""` | Recommended |

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py              # Application factory and configuration
│   ├── config.py            # Settings and environment variables
│   ├── dependencies.py      # Dependency injection helpers
│   ├── api/
│   │   ├── __init__.py
│   │   └── health.py        # Health check endpoint
│   └── services/
│       ├── __init__.py
│       └── firestore_service.py  # Firestore client and connectivity
├── tests/
│   ├── __init__.py
│   ├── test_health.py       # Health endpoint tests
│   ├── test_config.py       # Configuration tests
│   ├── test_logging.py      # Logging tests
│   └── test_firestore_service.py  # Firestore service tests
├── .env.example             # Example environment configuration
├── pyproject.toml           # Poetry dependencies and project metadata
├── poetry.lock              # Locked dependency versions
└── README.md                # This file
```

## Logging

The service uses JSON-structured logging with the following fields:
- `timestamp`: ISO 8601 timestamp
- `level`: Log level (INFO, WARNING, ERROR, etc.)
- `service`: Service name from configuration
- `message`: Log message

The logger gracefully handles unicode and binary payloads without raising exceptions.

## Firestore Integration

The service includes a Firestore integration module (`app.services.firestore_service`) that provides:

### Features

- **Singleton Client**: Uses `@lru_cache` to ensure only one Firestore client instance is created
- **ADC Support**: Automatically uses Application Default Credentials for authentication
- **Configuration Validation**: Verifies `FIRESTORE_PROJECT_ID` is set before attempting to connect
- **Smoke Test**: Built-in connectivity test that writes, reads, and cleans up a test document
- **Error Handling**: Provides actionable error messages for common configuration issues

### Usage

**Get Firestore Client (via Dependency Injection)**

```python
from fastapi import Depends
from google.cloud import firestore
from app.dependencies import get_firestore_client

@app.get("/example")
async def example_endpoint(client: firestore.Client = Depends(get_firestore_client)):
    # Use the client
    doc_ref = client.collection("plans").document("doc_id")
    doc_ref.set({"data": "value"})
```

**Direct Usage**

```python
from app.services.firestore_service import get_client, smoke_test

# Get client
client = get_client()

# Run smoke test
smoke_test(client)  # Or smoke_test() to use default client
```

### Running the Smoke Test

To verify Firestore connectivity, you can run the smoke test:

```python
from app.services.firestore_service import smoke_test

try:
    smoke_test()
    print("✅ Firestore connectivity verified")
except Exception as e:
    print(f"❌ Firestore connectivity failed: {e}")
```

The smoke test:
1. Writes a test document to `plans_dev_test` collection with a unique ID
2. Reads the document back to verify connectivity
3. Deletes the test document to clean up
4. Uses unique document IDs to avoid conflicts in concurrent tests

### Using Firestore Emulator (Optional)

For local development without GCP credentials, you can use the Firestore emulator:

```bash
# Install the emulator
gcloud components install cloud-firestore-emulator

# Start the emulator
gcloud beta emulators firestore start --host-port=localhost:8080

# In another terminal, set the emulator environment variable
export FIRESTORE_EMULATOR_HOST=localhost:8080
export FIRESTORE_PROJECT_ID=test-project

# Run your application
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Note**: When using the emulator, you don't need `GOOGLE_APPLICATION_CREDENTIALS` set.

### Error Messages

The Firestore service provides clear, actionable error messages:

- **Missing `FIRESTORE_PROJECT_ID`**: Tells you to set the environment variable
- **Missing ADC**: Provides instructions to set `GOOGLE_APPLICATION_CREDENTIALS` or use `gcloud auth application-default login`
- **Connectivity Failures**: Indicates network issues, permission problems, or service unavailability
- **Permission Errors**: Suggests checking IAM roles and permissions

## API Endpoints

### Health Check

**GET /health**

Returns the health status of the service.

Response:
```json
{
  "status": "ok"
}
```

## Error Handling

- **Invalid PORT**: Non-integer or out-of-range PORT values (not 1-65535) will raise a clear validation error
- **Missing environment variables**: Critical missing values will log warnings but allow startup with defaults
- **Logging errors**: Unicode/binary encoding issues in logs are caught and formatted safely

## Cloud Run Deployment

This service is designed to run on Google Cloud Run:

1. The `PORT` environment variable is automatically set by Cloud Run
2. JSON logging is Cloud Logging compatible
3. Health checks are available at `/health`
4. The service gracefully handles startup and shutdown signals

## Development Notes

- The app factory pattern (`create_app()`) allows multiple app instances for testing
- Settings are cached using `@lru_cache()` to avoid repeated environment reads
- All endpoints use async handlers for optimal performance
- The health router is extensible for adding readiness/liveness probes



# Permanents (License, Contributing, Author)

Do not change any of the below sections

## License

This Agent Foundry Project is licensed under the Apache 2.0 License - see the LICENSE file for details.

## Contributing

Feel free to submit issues and enhancement requests!

## Author

Created by Agent Foundry and John Brosnihan

