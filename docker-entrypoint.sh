#!/bin/sh
# Docker entrypoint script for plan-scheduler
# Starts uvicorn with environment-based configuration

set -e

# Validate and set defaults for environment variables
PORT="${PORT:-8080}"
WORKERS="${WORKERS:-1}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Validate PORT is a number between 1 and 65535
if ! echo "$PORT" | grep -qE '^[0-9]+$' || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "Error: PORT must be a number between 1 and 65535, got: ${PORT}" >&2
    exit 1
fi

# Validate WORKERS is a positive integer
if ! echo "$WORKERS" | grep -qE '^[0-9]+$' || [ "$WORKERS" -lt 1 ]; then
    echo "Error: WORKERS must be a positive integer, got: ${WORKERS}" >&2
    exit 1
fi

# Convert LOG_LEVEL to lowercase for uvicorn
LOG_LEVEL_LOWER=$(echo "${LOG_LEVEL}" | tr '[:upper:]' '[:lower:]')

# Validate LOG_LEVEL is one of the valid uvicorn log levels
case "$LOG_LEVEL_LOWER" in
    critical|error|warning|info|debug|trace)
        ;;
    *)
        echo "Error: LOG_LEVEL must be one of: critical, error, warning, info, debug, trace (case insensitive), got: ${LOG_LEVEL}" >&2
        exit 1
        ;;
esac

# Start uvicorn with validated configuration
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    --log-level "${LOG_LEVEL_LOWER}"
