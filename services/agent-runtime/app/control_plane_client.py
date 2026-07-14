"""Client for communicating with the control plane service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from shared_schemas.policy import PolicyDecision, PolicyRequest
from shared_schemas.tool import ToolSchema


class ControlPlaneClient:
    """HTTP client for the control plane."""

    def __init__(self, base_url: str = settings.control_plane_url):
        self.base_url = base_url.rstrip("/")
        self._token: str | None = None

    async def authenticate(self) -> str:
        """Authenticate and get a JWT token."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/auth/token",
                data={
                    "client_id": settings.agent_client_id,
                    "client_secret": settings.agent_client_secret,
                },
            )
            response.raise_for_status()
            data = response.json()
            self._token = data["access_token"]
            return self._token

    async def _ensure_token(self):
        if not self._token:
            await self.authenticate()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def check_policy(self, request: PolicyRequest) -> PolicyDecision:
        """Check if an action is allowed by policy."""
        await self._ensure_token()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{self.base_url}/policy/check",
                json=request.model_dump(mode="json"),
                headers={"Authorization": f"Bearer {self._token}"},
            )
            response.raise_for_status()
            return PolicyDecision(**response.json())

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def get_tool_schemas(self, gateway_url: str = settings.tool_gateway_url) -> list[ToolSchema]:
        """Fetch available tool schemas from the tool gateway."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{gateway_url}/tools")
            response.raise_for_status()
            return [ToolSchema(**t) for t in response.json()]
