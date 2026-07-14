"""CRM backend client — communicates with the CRM service."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


class CRMClient:
    """Client for the CRM backend service."""

    def __init__(self, base_url: str = settings.crm_service_url):
        self.base_url = base_url.rstrip("/")

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def lookup_customer(self, customer_id: str) -> dict[str, Any]:
        """Look up a customer by ID."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.base_url}/customers/{customer_id}")
            if response.is_success:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"CRM lookup failed: {response.status_code} - {response.text}",
                }

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=3))
    async def add_note(self, customer_id: str, note: str) -> dict[str, Any]:
        """Add a note to a customer record."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{self.base_url}/customers/{customer_id}/notes",
                json={"note": note},
            )
            if response.is_success:
                return {"success": True, "data": response.json()}
            else:
                return {
                    "success": False,
                    "error": f"CRM add note failed: {response.status_code} - {response.text}",
                }
