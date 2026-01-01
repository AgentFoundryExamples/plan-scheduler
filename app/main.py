# Copyright 2025 John Brosnihan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""FastAPI application factory and configuration."""

import logging
import sys
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from pythonjsonlogger.json import JsonFormatter
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import health, plans, pubsub
from app.config import get_settings


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add request correlation IDs to all requests.

    Extracts or generates a unique request ID and makes it available
    in the request state for logging and tracing purposes.
    """

    async def dispatch(self, request: Request, call_next):
        """Process request and add correlation ID."""
        # Extract X-Request-ID from headers or generate a new one
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Store in request state for access in route handlers
        request.state.request_id = request_id

        # Add to logging context
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.request_id = request_id
            return record

        logging.setLogRecordFactory(record_factory)

        try:
            response = await call_next(request)
            # Add request ID to response headers for tracing
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            # Restore original factory
            logging.setLogRecordFactory(old_factory)


def setup_logging() -> None:
    """
    Configure JSON-structured logging for the application.

    Sets up a JSON formatter that includes timestamp, level, message,
    service name, and request context fields for all log entries.
    Uses LOG_LEVEL from configuration with fallback to INFO.
    """
    settings = get_settings()

    # Map string log level to logging constant
    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)

    # Create JSON formatter with custom format
    class CustomJsonFormatter(JsonFormatter):
        """Custom JSON formatter that adds service name and handles encoding issues."""

        def add_fields(self, log_record, record, message_dict):
            """Add custom fields to log records."""
            super().add_fields(log_record, record, message_dict)
            log_record["service"] = settings.SERVICE_NAME
            # Add request_id if available
            if hasattr(record, "request_id"):
                log_record["request_id"] = record.request_id

        def format(self, record):
            """Format log record, handling unicode and binary payloads gracefully."""
            try:
                return super().format(record)
            except (UnicodeDecodeError, UnicodeEncodeError, TypeError) as e:
                # If formatting fails, create a safe fallback log entry
                safe_record = {
                    "service": settings.SERVICE_NAME,
                    "timestamp": self.formatTime(record, self.datefmt),
                    "level": record.levelname,
                    "message": f"[Encoding error: {str(e)}] {repr(record.msg)}",
                    "error": str(e),
                }
                return self.serialize_log_record(safe_record)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    formatter = CustomJsonFormatter(
        fmt="%(timestamp)s %(levelname)s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Log startup
    root_logger.info(
        f"Logging configured for service: {settings.SERVICE_NAME}, level: {settings.LOG_LEVEL}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Handles startup and shutdown events.
    """
    logger = logging.getLogger(__name__)
    logger.info("Application starting up")
    yield
    logger.info("Application shutting down")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        FastAPI: Configured FastAPI application instance
    """
    # Setup logging first
    setup_logging()

    settings = get_settings()
    logger = logging.getLogger(__name__)

    # Create FastAPI app with metadata
    app = FastAPI(
        title="Plan Scheduler Service",
        description="FastAPI service for plan scheduling with Firestore integration",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Add request correlation middleware
    app.add_middleware(RequestCorrelationMiddleware)

    # Include routers
    app.include_router(health.router)
    app.include_router(plans.router)
    app.include_router(pubsub.router)

    logger.info(
        f"Application created: service={settings.SERVICE_NAME}, "
        f"port={settings.PORT}, workers={settings.WORKERS}, log_level={settings.LOG_LEVEL}"
    )

    return app


def get_app() -> FastAPI:
    """
    Get or create the application instance.

    This function is used by the ASGI server to import the app.
    It ensures the app is only created when actually needed.
    """
    return create_app()


# Create app instance for ASGI server to import
# This is required for uvicorn to find the app with "app.main:app"
app = get_app()
