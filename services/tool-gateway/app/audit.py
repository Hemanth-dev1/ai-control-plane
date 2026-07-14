"""Audit logging — Kafka producer for tool invocation audit events."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog
from aiokafka import AIOKafkaProducer

from app.config import settings
from shared_schemas.events import AuditEvent, EventType

logger = structlog.get_logger(__name__)


class AuditProducer:
    """Kafka producer for audit events from the tool gateway."""

    def __init__(self):
        self._producer: AIOKafkaProducer | None = None
        self._connected = False

    async def connect(self):
        """Connect to Kafka."""
        if self._connected:
            return
        try:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
            await self._producer.start()
            self._connected = True
            logger.info("kafka_connected", topic="tool.invocations")
        except Exception as e:
            logger.warning("kafka_connection_failed", error=str(e))
            self._connected = False

    async def emit_tool_invocation(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        agent_id: UUID,
        run_id: UUID | None,
        success: bool,
        result: Any = None,
        error: str | None = None,
        duration_ms: float = 0.0,
        correlation_id: str | None = None,
    ):
        """Emit a tool invocation audit event to Kafka."""
        event = AuditEvent(
            event_type=EventType.TOOL_INVOCATION,
            source_service=settings.service_name,
            correlation_id=correlation_id,
            payload={
                "tool_name": tool_name,
                "arguments": arguments,
                "success": success,
                "result": result,
                "error": error,
                "duration_ms": duration_ms,
            },
            agent_id=agent_id,
            run_id=run_id,
        )

        await self._send("tool.invocations", event)

    async def emit_policy_decision(
        self,
        agent_id: UUID,
        tool_name: str,
        allowed: bool,
        reason: str,
        correlation_id: str | None = None,
    ):
        """Emit a policy decision audit event."""
        event = AuditEvent(
            event_type=EventType.POLICY_DECISION,
            source_service=settings.service_name,
            correlation_id=correlation_id,
            payload={
                "tool_name": tool_name,
                "allowed": allowed,
                "reason": reason,
            },
            agent_id=agent_id,
        )

        await self._send("policy.decisions", event)

    async def _send(self, topic: str, event: AuditEvent):
        """Send an event to a Kafka topic."""
        if not self._connected:
            await self.connect()

        if self._producer and self._connected:
            try:
                await self._producer.send(topic, event.model_dump(mode="json"))
                logger.debug("audit_event_sent", topic=topic, event_id=str(event.event_id))
            except Exception as e:
                logger.error("audit_event_failed", topic=topic, error=str(e))
        else:
            logger.warning("audit_event_dropped", topic=topic, reason="kafka_not_connected")

    async def close(self):
        """Close the Kafka producer."""
        if self._producer:
            await self._producer.stop()
            self._connected = False
