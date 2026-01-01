#!/bin/sh
# Docker entrypoint script for plan-scheduler
# Starts uvicorn with environment-based configuration

set -e

# Convert LOG_LEVEL to lowercase for uvicorn
LOG_LEVEL_LOWER=$(echo "${LOG_LEVEL}" | tr '[:upper:]' '[:lower:]')

# Start uvicorn with configuration from environment variables
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    --log-level "${LOG_LEVEL_LOWER}"
