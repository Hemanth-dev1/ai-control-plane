"""Notification backend client — communicates with the notification service."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


class NotificationClient:
    """Client for the notification backend service."""

    def __init__(self, base_url: str = settings.notification_service_url):
        self.base_url = base_url.rstrip("/")

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def send_message(
        self,
        recipient: str,
        subject: str,
        message: str,
        channel: str = "email",
    ) -> dict[str, Any]:
        """Send a notification message."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {
                "recipient": recipient,
                "subject": subject,
                "message": message,
                "channel": channel,
            }

            response = await client.post(f"{self.base_url}/notifications", json=payload)
            if response.is_success:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"Notification failed: {response.status_code} - {response.text}",
                }
