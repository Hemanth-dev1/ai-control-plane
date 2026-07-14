"""Structured JSON logging configuration for all services.

Import from this module in every service's startup:
    from shared_schemas.logging_config import setup_logging
    setup_logging("service-name", "INFO")
"""

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(service_name: str = "unknown", log_level: str = "INFO") -> None:
    """Configure structlog for structured JSON logging.

    Call this once at service startup before any loggers are used.
    """
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set root logger level
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Remove default handlers to avoid duplicate output
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add a handler that outputs to stderr (Docker convention)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
        )
    )
    root_logger.addHandler(handler)

    # Suppress noisy third-party loggers
    for logger_name in ("uvicorn.access", "uvicorn.error", "httpx"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
