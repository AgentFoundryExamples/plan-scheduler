# --- Build stage ---
# This stage installs poetry and exports the dependencies to requirements.txt
FROM python:3.12-slim as builder

WORKDIR /app

# Install poetry
RUN pip install --no-cache-dir poetry==1.8.2

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

# Copy requirements.txt from the builder stage
COPY --from=builder /app/requirements.txt ./

# Install dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app

# Expose port 8080 (Cloud Run default)
EXPOSE 8080

# Set environment variable for port (Cloud Run will override this)
ENV PORT=8080

# Health check (optional but recommended for Cloud Run)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" || exit 1

# Run the application with uvicorn
# --host 0.0.0.0 allows external connections (required for Cloud Run)
# --port uses the PORT environment variable (Cloud Run compatibility)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
