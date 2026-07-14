"""Tests for the policy engine client."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.policy import PolicyEngine
from shared_schemas.policy import PolicyRequest


@pytest.mark.asyncio
async def test_policy_engine_unreachable_denies():
    """When OPA is unreachable, policy should deny by default (fail-closed)."""
    engine = PolicyEngine(opa_url="http://localhost:19999")  # non-routable port
    request = PolicyRequest(
        agent_id=uuid4(),
        tool_name="crm.lookup_customer",
        arguments={"customer_id": "123"},
    )

    decision = await engine.check(request)
    assert decision.allowed is False
    assert "error" in decision.reason.lower()
