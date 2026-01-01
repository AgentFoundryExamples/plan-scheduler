.PHONY: help install test lint format docker-build docker-run docker-run-test docker-stop clean pre-commit-install

# Default target - show help
help:
	@echo "Plan Scheduler Service - Makefile Commands"
	@echo ""
	@echo "Development commands:"
	@echo "  make install             Install project dependencies using Poetry"
	@echo "  make test                Run all tests with pytest"
	@echo "  make test-cov            Run tests with coverage report"
	@echo "  make lint                Run ruff linter"
	@echo "  make format              Format code with black"
	@echo "  make format-check        Check code formatting without making changes"
	@echo ""
	@echo "Docker commands:"
	@echo "  make docker-build        Build Docker image"
	@echo "  make docker-run          Run Docker container (requires .env file)"
	@echo "  make docker-run-test     Run Docker container for local testing (no credentials required)"
	@echo "  make docker-stop         Stop running Docker container"
	@echo "  make docker-logs         Show Docker container logs"
	@echo "  make docker-test         Build and run container for testing, then show logs"
	@echo ""
	@echo "Pre-commit hooks (optional):"
	@echo "  make pre-commit-install  Install pre-commit hooks"
	@echo "  make pre-commit-run      Run pre-commit hooks on all files"
	@echo ""
	@echo "Utility commands:"
	@echo "  make clean               Remove cache files and artifacts"
	@echo "  make run                 Run the service locally with uvicorn"

# Install dependencies
install:
	@echo "Installing dependencies with Poetry..."
	poetry install

# Run tests
test:
	@echo "Running tests..."
	poetry run pytest

# Run tests with coverage
test-cov:
	@echo "Running tests with coverage..."
	poetry run pytest --cov=app --cov-report=term-missing

# Run linter (ruff)
lint:
	@echo "Running ruff linter..."
	poetry run ruff check app tests

# Format code with black
format:
	@echo "Formatting code with black..."
	poetry run black app tests

# Check formatting without making changes
format-check:
	@echo "Checking code formatting..."
	poetry run black --check app tests

# Build Docker image
docker-build:
	@echo "Building Docker image..."
	docker build -t plan-scheduler:latest .

# Run Docker container
# Requires .env file for environment variables
docker-run:
	@if [ ! -f .env ]; then \
		echo "Error: .env file not found. Please create one from .env.example"; \
		exit 1; \
	fi
	@echo "Running Docker container..."
	@# Extract GOOGLE_APPLICATION_CREDENTIALS from .env if it exists
	@CREDS_PATH=$$(grep "^GOOGLE_APPLICATION_CREDENTIALS=" .env | cut -d '=' -f2); \
	VOLUME_MOUNT=""; \
	if [ -n "$$CREDS_PATH" ] && [ -f "$$CREDS_PATH" ]; then \
		VOLUME_MOUNT="-v $$CREDS_PATH:$$CREDS_PATH:ro"; \
		echo "Mounting credentials file: $$CREDS_PATH"; \
	fi; \
	docker run -d \
		--name plan-scheduler \
		--env-file .env \
		$$VOLUME_MOUNT \
		-p 8080:8080 \
		plan-scheduler:latest
	@echo "Container started. Access at http://localhost:8080"
	@echo "Use 'make docker-logs' to view logs"
	@echo "Use 'make docker-stop' to stop the container"

# Run Docker container for local testing without credentials
# This starts the container with minimal configuration for quick testing
docker-run-test:
	@echo "Running Docker container for local testing..."
	@echo "Note: This runs without Firestore credentials - some features will log warnings"
	docker run -d \
		--name plan-scheduler \
		-e PORT=8080 \
		-e LOG_LEVEL=INFO \
		-e WORKERS=1 \
		-e SERVICE_NAME=plan-scheduler \
		-e FIRESTORE_PROJECT_ID=test-project \
		-e PUBSUB_OIDC_ENABLED=false \
		-e PUBSUB_VERIFICATION_TOKEN=test-token \
		-p 8080:8080 \
		plan-scheduler:latest
	@echo ""
	@echo "Container started successfully!"
	@echo "Access the service at: http://localhost:8080"
	@echo "API Documentation: http://localhost:8080/docs"
	@echo "Health check: http://localhost:8080/health"
	@echo ""
	@echo "Test with: curl http://localhost:8080/health"
	@echo "Use 'make docker-logs' to view logs"
	@echo "Use 'make docker-stop' to stop the container"

# Stop Docker container
docker-stop:
	@echo "Stopping Docker container..."
	docker stop plan-scheduler || true
	docker rm plan-scheduler || true

# Show Docker container logs
docker-logs:
	docker logs -f plan-scheduler

# Build and test Docker container locally
# This is a convenience target that builds, runs, and shows logs
docker-test: docker-stop docker-build docker-run-test
	@echo ""
	@echo "Waiting 3 seconds for container to start..."
	@sleep 3
	@echo ""
	@echo "Testing health endpoint..."
	@curl -s http://localhost:8080/health || echo "Health check failed!"
	@echo ""
	@echo ""
	@echo "Checking container user (should be 'appuser')..."
	@docker exec plan-scheduler whoami || echo "User check failed!"
	@echo ""
	@echo "Container logs:"
	@docker logs plan-scheduler
	@echo ""
	@echo "Container is running. Use 'make docker-stop' to stop it."

# Install pre-commit hooks (optional)
pre-commit-install:
	@if [ -f .pre-commit-config.yaml ]; then \
		echo "Installing pre-commit hooks..."; \
		poetry run pre-commit install; \
	else \
		echo "Error: .pre-commit-config.yaml not found"; \
		exit 1; \
	fi

# Run pre-commit on all files
pre-commit-run:
	@if [ -f .pre-commit-config.yaml ]; then \
		echo "Running pre-commit on all files..."; \
		poetry run pre-commit run --all-files; \
	else \
		echo "Error: .pre-commit-config.yaml not found"; \
		exit 1; \
	fi

# Clean cache and artifacts
clean:
	@echo "Cleaning cache files and artifacts..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .coverage htmlcov 2>/dev/null || true
	@echo "Clean complete"

# Run service locally
run:
	@echo "Starting service locally..."
	poetry run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
