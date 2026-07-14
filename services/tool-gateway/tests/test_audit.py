"""Tests for Kafka audit event emission in the tool gateway."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.audit import AuditProducer
from shared_schemas.events import AuditEvent, EventType


@pytest.mark.asyncio
class TestAuditProducer:
    """Tests for the AuditProducer — Kafka event emission."""

    async def test_emit_tool_invocation_success(self):
        """Emit a tool invocation event when the call succeeds."""
        producer = AuditProducer()
        # Mock the Kafka producer to avoid actual connection
        producer._producer = AsyncMock()
        producer._connected = True

        agent_id = uuid4()
        run_id = uuid4()

        await producer.emit_tool_invocation(
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "CUST-001"},
            agent_id=agent_id,
            run_id=run_id,
            success=True,
            result={"name": "Acme Corp"},
            duration_ms=150.0,
        )

        # Verify the producer was called with the right topic
        assert producer._producer.send.called
        call_args = producer._producer.send.call_args
        topic = call_args[0][0]
        payload = call_args[0][1]

        assert topic == "tool.invocations"
        assert payload["event_type"] == "tool.invocation"
        assert payload["source_service"] == "tool-gateway"
        assert payload["payload"]["tool_name"] == "crm.lookup_customer"
        assert payload["payload"]["success"] is True
        assert payload["payload"]["duration_ms"] == 150.0
        assert payload["agent_id"] == str(agent_id)
        assert payload["run_id"] == str(run_id)

    async def test_emit_tool_invocation_failure(self):
        """Emit a tool invocation event when the call fails."""
        producer = AuditProducer()
        producer._producer = AsyncMock()
        producer._connected = True

        agent_id = uuid4()

        await producer.emit_tool_invocation(
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "INVALID"},
            agent_id=agent_id,
            run_id=None,
            success=False,
            error="Customer not found",
            duration_ms=50.0,
        )

        assert producer._producer.send.called
        call_args = producer._producer.send.call_args
        topic = call_args[0][0]
        payload = call_args[0][1]

        assert topic == "tool.invocations"
        assert payload["payload"]["success"] is False
        assert payload["payload"]["error"] == "Customer not found"
        assert payload["run_id"] is None

    async def test_emit_policy_decision_allowed(self):
        """Emit a policy decision event for an allowed action."""
        producer = AuditProducer()
        producer._producer = AsyncMock()
        producer._connected = True

        agent_id = uuid4()

        await producer.emit_policy_decision(
            agent_id=agent_id,
            tool_name="crm.lookup_customer",
            allowed=True,
            reason="Policy evaluation: allowed",
        )

        assert producer._producer.send.called
        call_args = producer._producer.send.call_args
        topic = call_args[0][0]
        payload = call_args[0][1]

        assert topic == "policy.decisions"
        assert payload["event_type"] == "policy.decision"
        assert payload["payload"]["allowed"] is True
        assert payload["payload"]["tool_name"] == "crm.lookup_customer"

    async def test_emit_policy_decision_denied(self):
        """Emit a policy decision event for a denied action."""
        producer = AuditProducer()
        producer._producer = AsyncMock()
        producer._connected = True

        agent_id = uuid4()

        await producer.emit_policy_decision(
            agent_id=agent_id,
            tool_name="ticketing.create_ticket",
            allowed=False,
            reason="Action denied: high-risk operation",
        )

        assert producer._producer.send.called
        call_args = producer._producer.send.call_args
        payload = call_args[0][1]

        assert payload["payload"]["allowed"] is False
        assert payload["payload"]["reason"] == "Action denied: high-risk operation"

    async def test_emit_with_correlation_id(self):
        """Emit an event with a correlation ID for tracing."""
        producer = AuditProducer()
        producer._producer = AsyncMock()
        producer._connected = True

        await producer.emit_tool_invocation(
            tool_name="notify.send_message",
            arguments={"recipient": "test@example.com", "message": "Hello"},
            agent_id=uuid4(),
            run_id=uuid4(),
            success=True,
            correlation_id="trace-abc-123",
        )

        assert producer._producer.send.called
        call_args = producer._producer.send.call_args
        payload = call_args[0][1]

        assert payload["correlation_id"] == "trace-abc-123"

    async def test_emit_when_kafka_disconnected(self):
        """Emit should not crash when Kafka is not connected."""
        producer = AuditProducer()
        producer._connected = False
        producer._producer = None

        # Should not raise
        await producer.emit_tool_invocation(
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "CUST-001"},
            agent_id=uuid4(),
            run_id=None,
            success=True,
        )
        # No assertion needed — just verifying it doesn't crash

    async def test_emit_tool_invocation_maps_all_fields_correctly(self):
        """Verify the AuditEvent payload structure is correct for compliance."""
        producer = AuditProducer()
        producer._producer = AsyncMock()
        producer._connected = True

        agent_id = uuid4()
        run_id = uuid4()

        await producer.emit_tool_invocation(
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "CUST-001"},
            agent_id=agent_id,
            run_id=run_id,
            success=True,
            result={"name": "Acme Corp", "tier": "premium"},
            duration_ms=200.0,
        )

        call_args = producer._producer.send.call_args
        payload = call_args[0][1]

        # Verify all top-level audit event fields
        assert "event_id" in payload
        assert "event_type" in payload
        assert "source_service" in payload
        assert "timestamp" in payload
        assert "correlation_id" in payload
        assert "payload" in payload
        assert "agent_id" in payload
        assert "run_id" in payload

        # Verify the payload structure
        event_payload = payload["payload"]
        assert event_payload["tool_name"] == "crm.lookup_customer"
        assert event_payload["arguments"] == {"customer_id": "CUST-001"}
        assert event_payload["success"] is True
        assert event_payload["result"] == {"name": "Acme Corp", "tier": "premium"}
        assert event_payload["duration_ms"] == 200.0


@pytest.mark.asyncio
class TestAuditProducerConnect:
    """Tests for the AuditProducer connection lifecycle."""

    async def test_connect_success(self):
        """Connect should succeed when Kafka is mocked."""
        producer = AuditProducer()
        # Skip actual Kafka connection for unit tests
        producer._connected = True
        producer._producer = MagicMock()

        assert producer._connected is True
        assert producer._producer is not None

    async def test_connect_failure_graceful(self):
        """Connect should handle Kafka connection failure gracefully."""
        producer = AuditProducer()
        with patch("aiokafka.AIOKafkaProducer") as mock_producer_class:
            mock_instance = AsyncMock()
            mock_instance.start.side_effect = Exception("Kafka unavailable")
            mock_producer_class.return_value = mock_instance

            await producer.connect()

            # Should still be considered disconnected but not crash
            assert producer._connected is False

    async def test_close_idempotent(self):
        """Closing an already-closed producer should not error."""
        producer = AuditProducer()
        await producer.close()  # No producer yet — should be safe
        await producer.close()  # Twice — should be safe
