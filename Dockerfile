# --- Build stage ---
# This stage installs poetry and exports the dependencies to requirements.txt
FROM python:3.12-slim AS builder

WORKDIR /app

# Install ca-certificates to handle SSL verification
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install poetry with pinned version for reproducible builds
# Using --trusted-host flags to handle environments with SSL inspection
RUN pip install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    poetry==1.8.2

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Export dependencies to requirements.txt
# --without-hashes is used for broader compatibility, especially with private indexes
# --only main ensures only production dependencies are included
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes --only main


# --- Final stage ---
# Use Python 3.12 slim image for a lightweight container
FROM python:3.12-slim

# Build arguments for configurable user/group IDs
# Default to 1000, but can be overridden at build time to avoid conflicts
# Example: docker build --build-arg APP_UID=10000 --build-arg APP_GID=10000 .
ARG APP_UID=1000
ARG APP_GID=1000

# Set working directory
WORKDIR /app

# Create non-root user and group with configurable UID/GID for security
# Using default UID/GID 1000, but configurable via build args
# Fail explicitly if UID/GID conflicts exist to prevent permission issues
RUN if getent group appuser >/dev/null 2>&1 && [ "$(getent group appuser | cut -d: -f3)" != "${APP_GID}" ]; then \
        echo "Error: Group 'appuser' already exists with a different GID. Please choose a different APP_GID." >&2; \
        exit 1; \
    elif getent group "${APP_GID}" >/dev/null 2>&1 && [ "$(getent group "${APP_GID}" | cut -d: -f1)" != "appuser" ]; then \
        echo "Error: GID ${APP_GID} is already in use by another group. Please choose a different APP_GID." >&2; \
        exit 1; \
    else \
        groupadd -r -g "${APP_GID}" appuser 2>/dev/null || true; \
    fi && \
    if getent passwd appuser >/dev/null 2>&1 && [ "$(getent passwd appuser | cut -d: -f3)" != "${APP_UID}" ]; then \
        echo "Error: User 'appuser' already exists with a different UID. Please choose a different APP_UID." >&2; \
        exit 1; \
    elif getent passwd "${APP_UID}" >/dev/null 2>&1 && [ "$(getent passwd "${APP_UID}" | cut -d: -f1)" != "appuser" ]; then \
        echo "Error: UID ${APP_UID} is already in use by another user. Please choose a different APP_UID." >&2; \
        exit 1; \
    else \
        useradd -r -u "${APP_UID}" -g "${APP_GID}" -s /sbin/nologin -c "Application user" appuser 2>/dev/null || true; \
    fi

# Copy requirements.txt from the builder stage
COPY --from=builder /app/requirements.txt ./

# Install dependencies from requirements.txt
# Using --trusted-host flags to handle environments with SSL inspection
RUN pip install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -r requirements.txt

# Copy application code and entrypoint script
COPY app ./app
COPY docker-entrypoint.sh ./

# Make entrypoint script executable and set ownership
RUN chmod +x docker-entrypoint.sh && \
    chown -R appuser:appuser /app

# Expose port 8080 (Cloud Run default)
EXPOSE 8080

# Set environment variables for Cloud Run compatibility
# PORT: Cloud Run will override this with the actual port assignment
# LOG_LEVEL: Controls logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
# WORKERS: Number of uvicorn worker processes (1-2 recommended for Cloud Run)
ENV PORT=8080 \
    LOG_LEVEL=INFO \
    WORKERS=1

# Switch to non-root user for security
# All subsequent commands and the application will run as this user
USER appuser

# Use entrypoint script to start uvicorn with proper configuration
# This avoids shell injection vulnerabilities from using sh -c with CMD
ENTRYPOINT ["./docker-entrypoint.sh"]
