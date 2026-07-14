"""Database migration runner — applies Alembic migrations at service startup.

This module provides a `run_migrations()` async function that the startup
event handler calls instead of `Base.metadata.create_all`.

For local development / manual runs:
    cd services/control-plane
    PYTHONPATH=. alembic upgrade head
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import structlog
from alembic import command
from alembic.config import Config as AlembicConfig

from app.config import settings

logger = structlog.get_logger(__name__)


def get_alembic_config() -> AlembicConfig:
    """Get Alembic configuration pointing to the ini file relative to this project."""
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    alc = AlembicConfig(str(alembic_ini))
    alc.set_main_option("sqlalchemy.url", settings.database_url_sync)

    # Allow override from environment (useful in Docker/CI)
    if env_url := os.environ.get("DATABASE_URL_SYNC"):
        alc.set_main_option("sqlalchemy.url", env_url)
    elif env_url := os.environ.get("DATABASE_URL", ""):
        # Strip the +asyncpg to get a sync URL
        alc.set_main_option("sqlalchemy.url", env_url.replace("+asyncpg", ""))

    return alc


def run_migrations() -> None:
    """Apply all pending Alembic migrations (blocking — runs in executor)."""
    try:
        alc = get_alembic_config()
        command.upgrade(alc, "head")
        logger.info("database_migrations_applied")
    except Exception as e:
        logger.error("database_migration_failed", error=str(e))
        raise


async def run_migrations_async() -> None:
    """Apply all pending Alembic migrations (async wrapper)."""
    await asyncio.to_thread(run_migrations)
