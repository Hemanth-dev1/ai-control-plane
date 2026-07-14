"""Mock notification service — publishes messages to Kafka."""

from __future__ import annotations

import json
from datetime import datetime

import structlog
from aiokafka import AIOKafkaProducer
from fastapi import FastAPI
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

app = FastAPI(title="Notification Service", version="0.1.0")

# Kafka producer
producer: AIOKafkaProducer | None = None


class NotificationRequest(BaseModel):
    recipient: str
    subject: str
    message: str
    channel: str = "email"


@app.on_event("startup")
async def startup():
    global producer
    try:
        producer = AIOKafkaProducer(
            bootstrap_servers="kafka:9092",
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await producer.start()
        logger.info("notification_service_started", kafka_connected=True)
    except Exception as e:
        logger.warning("notification_service_started", kafka_connected=False, error=str(e))
        producer = None


@app.on_event("shutdown")
async def shutdown():
    if producer:
        await producer.stop()


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "notification-service"}


@app.post("/notifications")
async def send_notification(notification: NotificationRequest):
    """Send a notification by publishing to Kafka."""
    event = {
        "type": "notification.outbound",
        "timestamp": datetime.utcnow().isoformat(),
        "payload": notification.model_dump(),
    }

    if producer:
        try:
            await producer.send("notifications.outbound", event)
            logger.info(
                "notification_published",
                recipient=notification.recipient,
                channel=notification.channel,
            )
        except Exception as e:
            logger.error("notification_publish_failed", error=str(e))
            return {
                "success": False,
                "error": f"Failed to publish notification: {e}",
                "message": "Notification queued (simulated)",
            }

    return {
        "success": True,
        "message": f"Notification sent to {notification.recipient} via {notification.channel}",
        "recipient": notification.recipient,
        "subject": notification.subject,
        "channel": notification.channel,
    }
