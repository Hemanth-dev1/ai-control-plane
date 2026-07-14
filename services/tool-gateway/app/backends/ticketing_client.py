"""Ticketing backend client — communicates with the ticketing service."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


class TicketingClient:
    """Client for the ticketing backend service."""

    def __init__(self, base_url: str = settings.ticketing_service_url):
        self.base_url = base_url.rstrip("/")

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def create_ticket(
        self,
        title: str,
        description: str,
        priority: str = "medium",
        customer_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new support ticket."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload = {
                "title": title,
                "description": description,
                "priority": priority,
            }
            if customer_id:
                payload["customer_id"] = customer_id

            response = await client.post(f"{self.base_url}/tickets", json=payload)
            if response.is_success:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"Ticket creation failed: {response.status_code} - {response.text}",
                }

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        """Get a ticket by ID."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.base_url}/tickets/{ticket_id}")
            if response.is_success:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"Ticket lookup failed: {response.status_code} - {response.text}",
                }
