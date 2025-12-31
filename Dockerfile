# Use Python 3.12 slim image for a lightweight container
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first (better layer caching)
COPY pyproject.toml poetry.lock ./

# Install dependencies directly from lock file using pip
# This avoids needing Poetry in the container
RUN pip install --no-cache-dir \
    fastapi==0.115.14 \
    uvicorn[standard]==0.34.3 \
    pydantic==2.10.5 \
    pydantic-settings==2.12.0 \
    python-json-logger==3.3.0 \
    google-cloud-firestore==2.22.0

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
