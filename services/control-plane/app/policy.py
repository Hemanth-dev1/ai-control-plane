"""Policy engine integration — calls OPA (Open Policy Agent) for authorization decisions."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from shared_schemas.policy import PolicyDecision, PolicyRequest


class PolicyEngine:
    """Client for OPA (Open Policy Agent) policy decisions."""

    def __init__(self, opa_url: str = settings.opa_url):
        self.opa_url = opa_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=5.0)
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
    )
    async def check(self, request: PolicyRequest) -> PolicyDecision:
        """Evaluate a policy request against OPA."""
        client = await self._get_client()

        input_data = {
            "agent_id": str(request.agent_id),
            "tool_name": request.tool_name,
            "arguments": request.arguments,
        }

        try:
            response = await client.post(
                f"{self.opa_url}/v1/data/control_plane/allow",
                json={"input": input_data},
            )
            response.raise_for_status()
            result = response.json()

            allowed = result.get("result", False)
            decision_id = str(uuid.uuid4())

            if allowed:
                return PolicyDecision(
                    allowed=True,
                    reason="Policy evaluation: allowed",
                    decision_id=decision_id,
                    request_id=request.request_id,
                )
            else:
                # Try to get the deny reason
                deny_response = await client.post(
                    f"{self.opa_url}/v1/data/control_plane/deny_reason",
                    json={"input": input_data},
                )
                reason = "Action denied by policy"
                if deny_response.is_success:
                    deny_result = deny_response.json()
                    if deny_result.get("result"):
                        reason = deny_result["result"]

                return PolicyDecision(
                    allowed=False,
                    reason=reason,
                    decision_id=decision_id,
                    request_id=request.request_id,
                )

        except httpx.HTTPError as e:
            # If OPA is unreachable or returns an error, deny by default (fail-closed)
            return PolicyDecision(
                allowed=False,
                reason=f"Policy engine error: {e}",
                decision_id=str(uuid.uuid4()),
                request_id=request.request_id,
            )

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
