"""Audit Consumer — reads all four Kafka topics and writes a flattened audit trail.

This consumer reads from:
  - policy.decisions
  - agent.executions
  - tool.invocations
  - notifications.outbound

And writes a structured, queryable audit log to stdout (JSON lines) and optionally
to OpenSearch (when available). In production, this would back a compliance dashboard.
"""

from __future__ import annotations

import asyncio
import json
import signal
import sys
from datetime import datetime

import structlog
from aiokafka import AIOKafkaConsumer

logger = structlog.get_logger(__name__)

TOPICS = [
    "policy.decisions",
    "agent.executions",
    "tool.invocations",
    "notifications.outbound",
]

KAFKA_BOOTSTRAP_SERVERS = "kafka:9092"
GROUP_ID = "audit-consumer"


def setup_logging():
    """Configure JSON logging for the audit consumer."""
    import logging

    timestamper = structlog.processors.TimeStamper(fmt="iso")
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            timestamper,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    logging.getLogger("aiokafka").setLevel(logging.WARNING)


def write_audit_record(topic: str, event: dict) -> None:
    """Write a flattened audit record to stdout as JSON."""
    record = {
        "@timestamp": datetime.utcnow().isoformat(),
        "topic": topic,
        "event_id": event.get("event_id", ""),
        "event_type": event.get("event_type", ""),
        "source_service": event.get("source_service", ""),
        "agent_id": str(event.get("agent_id", "")),
        "run_id": str(event.get("run_id", "")),
        "correlation_id": event.get("correlation_id", ""),
        "payload": event.get("payload", {}),
    }
    sys.stdout.write(json.dumps(record) + "\n")
    sys.stdout.flush()


async def consume():
    """Main consumer loop."""
    consumer = AIOKafkaConsumer(
        *TOPICS,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=GROUP_ID,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: json.loads(v.decode()) if v else None,
    )

    shutdown_event = asyncio.Event()

    def _signal_handler():
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await consumer.start()
        logger.info("audit_consumer_started", topics=TOPICS)

        while not shutdown_event.is_set():
            try:
                msg_set = await consumer.getmany(timeout_ms=1000)
                for topic, messages in msg_set.items():
                    for msg in messages:
                        if msg.value:
                            write_audit_record(topic, msg.value)
            except Exception as e:
                logger.error("consume_error", error=str(e))

    except Exception as e:
        logger.error("consumer_fatal", error=str(e))
    finally:
        await consumer.stop()
        logger.info("audit_consumer_stopped")


if __name__ == "__main__":
    setup_logging()
    logger.info("audit_consumer_booting", kafka=KAFKA_BOOTSTRAP_SERVERS)
    asyncio.run(consume())
