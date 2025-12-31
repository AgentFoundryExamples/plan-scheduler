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
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pythonjsonlogger.json import JsonFormatter

from app.api import health
from app.config import get_settings


def setup_logging() -> None:
    """
    Configure JSON-structured logging for the application.
    
    Sets up a JSON formatter that includes timestamp, level, message,
    and service name for all log entries.
    """
    settings = get_settings()
    
    # Create JSON formatter with custom format
    class CustomJsonFormatter(JsonFormatter):
        """Custom JSON formatter that adds service name and handles encoding issues."""
        
        def add_fields(self, log_record, record, message_dict):
            """Add custom fields to log records."""
            super().add_fields(log_record, record, message_dict)
            log_record['service'] = settings.SERVICE_NAME
        
        def format(self, record):
            """Format log record, handling unicode and binary payloads gracefully."""
            try:
                return super().format(record)
            except (UnicodeDecodeError, UnicodeEncodeError, TypeError) as e:
                # If formatting fails, create a safe fallback log entry
                safe_record = {
                    'service': settings.SERVICE_NAME,
                    'timestamp': self.formatTime(record, self.datefmt),
                    'level': record.levelname,
                    'message': f'[Encoding error: {str(e)}] {repr(record.msg)}',
                    'error': str(e)
                }
                return self.serialize_log_record(safe_record)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler with JSON formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    
    formatter = CustomJsonFormatter(
        fmt='%(timestamp)s %(levelname)s %(name)s %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S'
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    # Log startup
    root_logger.info(f"Logging configured for service: {settings.SERVICE_NAME}")


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
        openapi_url="/openapi.json"
    )
    
    # Include routers
    app.include_router(health.router)
    
    logger.info(
        f"Application created: service={settings.SERVICE_NAME}, "
        f"port={settings.PORT}"
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
