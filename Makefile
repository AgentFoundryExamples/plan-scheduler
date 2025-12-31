.PHONY: help install test lint format docker-build docker-run docker-stop clean pre-commit-install

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
	@echo "  make docker-stop         Stop running Docker container"
	@echo "  make docker-logs         Show Docker container logs"
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

# Stop Docker container
docker-stop:
	@echo "Stopping Docker container..."
	docker stop plan-scheduler || true
	docker rm plan-scheduler || true

# Show Docker container logs
docker-logs:
	docker logs -f plan-scheduler

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
