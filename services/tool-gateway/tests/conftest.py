"""Shared fixtures for tool-gateway integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import prometheus_client
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    """Clear Prometheus metrics registry before each test.

    Prevents ``ValueError: Duplicated timeseries in CollectorRegistry``
    when tests create or load modules that register the same metric more
    than once across test runs.
    """
    collectors = list(prometheus_client.REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            prometheus_client.REGISTRY.unregister(collector)
        except KeyError:
            pass
    # Reset the default collector to avoid stale state
    prometheus_client.REGISTRY._names_to_collectors.clear()
    prometheus_client.REGISTRY._collector_to_names.clear()


@pytest.fixture
def mock_kafka_producer():
    """Create a mock Kafka producer for testing.

    Patches the module-level ``audit_producer`` in ``app.main`` so that
    the actual requests use this mock instead of a real Kafka connection.
    """
    producer = AsyncMock()
    producer.emit_tool_invocation = AsyncMock()
    producer.emit_policy_decision = AsyncMock()
    producer.connect = AsyncMock()
    producer.close = AsyncMock()
    return producer


@pytest.fixture
def tool_gateway_app(mock_kafka_producer):
    """Create the tool-gateway FastAPI app, patching its Kafka producer.

    Uses ``unittest.mock.patch`` to replace the module-level global
    ``audit_producer`` in ``app.main`` so that every handler
    automatically uses the mock.
    """
    import app.main as main_module

    with patch.object(main_module, "audit_producer", mock_kafka_producer):
        yield main_module.app


@pytest.fixture
async def async_client(tool_gateway_app):
    """Create an async HTTP client against the tool-gateway app."""
    transport = ASGITransport(app=tool_gateway_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_agent_id() -> str:
    """Return a sample agent UUID string."""
    return str(uuid4())


@pytest.fixture
def sample_run_id() -> str:
    """Return a sample run UUID string."""
    return str(uuid4())
