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

# Set working directory
WORKDIR /app

# Create non-root user and group with specific UID/GID for security
# Using UID/GID 1000 as a common non-privileged user ID
RUN groupadd -r -g 1000 appuser && \
    useradd -r -u 1000 -g appuser -s /sbin/nologin -c "Application user" appuser

# Copy requirements.txt from the builder stage
COPY --from=builder /app/requirements.txt ./

# Install dependencies from requirements.txt
# Using --trusted-host flags to handle environments with SSL inspection
RUN pip install --no-cache-dir \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -r requirements.txt

# Copy application code
COPY app ./app

# Set ownership of application directory to non-root user
# This ensures the application can read its code and write temp files if needed
RUN chown -R appuser:appuser /app

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

# Run the application with uvicorn
# --host 0.0.0.0: Binds to all interfaces (required for Cloud Run)
# --port ${PORT}: Uses PORT environment variable (Cloud Run injects this)
# --workers ${WORKERS}: Configurable worker count (default 1 for Cloud Run)
# --log-level: Uses LOG_LEVEL environment variable (converted to lowercase for uvicorn)
# Note: Cloud Run health checks use the /health endpoint directly, no Docker HEALTHCHECK needed
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --log-level $(echo ${LOG_LEVEL} | tr '[:upper:]' '[:lower:]')"
