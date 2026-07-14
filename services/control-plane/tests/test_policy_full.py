"""Comprehensive tests for the policy-check flow — OPA client, fail-closed behavior, denial paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
import respx

from app.policy import PolicyEngine
from shared_schemas.policy import PolicyDecision, PolicyRequest


@pytest.mark.asyncio
class TestPolicyEngine:
    """Tests for PolicyEngine — the OPA client."""

    async def test_opa_allows_action(self):
        """When OPA returns allow=true, the decision should be allowed."""
        request = PolicyRequest(
            agent_id=uuid4(),
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "CUST-001"},
        )

        async with respx.mock:
            route = respx.post("http://localhost:8181/v1/data/control_plane/allow")
            route.respond(json={"result": True})

            engine = PolicyEngine(opa_url="http://localhost:8181")
            decision = await engine.check(request)

        assert decision.allowed is True
        assert "allowed" in decision.reason.lower()

    async def test_opa_denies_action(self):
        """When OPA returns allow=false, the decision should be denied."""
        request = PolicyRequest(
            agent_id=uuid4(),
            tool_name="ticketing.create_ticket",
            arguments={"title": "Test", "priority": "critical"},
        )

        async with respx.mock:
            # First call returns False
            allow_route = respx.post("http://localhost:8181/v1/data/control_plane/allow")
            allow_route.respond(json={"result": False})
            # Second call returns reason
            deny_route = respx.post("http://localhost:8181/v1/data/control_plane/deny_reason")
            deny_route.respond(json={"result": "Action denied: high-risk operation"})

            engine = PolicyEngine(opa_url="http://localhost:8181")
            decision = await engine.check(request)

        assert decision.allowed is False
        assert decision.reason

    async def test_opa_unreachable_denies_fail_closed(self):
        """When OPA is unreachable, policy should deny by default (fail-closed)."""
        engine = PolicyEngine(opa_url="http://localhost:19999")
        request = PolicyRequest(
            agent_id=uuid4(),
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "123"},
        )

        decision = await engine.check(request)
        assert decision.allowed is False
        assert "error" in decision.reason.lower()

    async def test_opa_http_error_denies(self):
        """When OPA returns a non-200 status, policy should deny."""
        request = PolicyRequest(
            agent_id=uuid4(),
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "CUST-001"},
        )

        async with respx.mock:
            route = respx.post("http://localhost:8181/v1/data/control_plane/allow")
            route.respond(status_code=500)

            engine = PolicyEngine(opa_url="http://localhost:8181")
            decision = await engine.check(request)

        # The httpx exception (HTTPStatusError) will cause fail-closed behavior
        assert decision.allowed is False

    async def test_opa_deny_reason_without_reason_endpoint(self):
        """If OPA denies but deny_reason endpoint fails, fallback message used."""
        request = PolicyRequest(
            agent_id=uuid4(),
            tool_name="notify.send_message",
            arguments={"recipient": "test@example.com", "subject": "Hi", "message": "Hello"},
        )

        async with respx.mock:
            allow_route = respx.post("http://localhost:8181/v1/data/control_plane/allow")
            allow_route.respond(json={"result": False})
            deny_route = respx.post("http://localhost:8181/v1/data/control_plane/deny_reason")
            deny_route.respond(status_code=500)

            engine = PolicyEngine(opa_url="http://localhost:8181")
            decision = await engine.check(request)

        assert decision.allowed is False
        # Should have a fallback reason
        assert decision.reason

    async def test_policy_decision_has_decision_id(self):
        """Every policy decision should have a unique decision_id."""
        request = PolicyRequest(
            agent_id=uuid4(),
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "CUST-001"},
        )

        async with respx.mock:
            route = respx.post("http://localhost:8181/v1/data/control_plane/allow")
            route.respond(json={"result": True})

            engine = PolicyEngine(opa_url="http://localhost:8181")
            decision = await engine.check(request)

        assert decision.decision_id
        assert len(decision.decision_id) > 0


@pytest.mark.asyncio
class TestPolicyAuthorizationDenialPaths:
    """Tests specifically for tool authorization denial paths."""

    async def test_engine_rejects_unknown_tool(self):
        """Policy should deny unknown/unregistered tools."""
        request = PolicyRequest(
            agent_id=uuid4(),
            tool_name="unknown.tool",
            arguments={},
        )

        async with respx.mock:
            route = respx.post("http://localhost:8181/v1/data/control_plane/allow")
            route.respond(json={"result": False})
            deny_route = respx.post("http://localhost:8181/v1/data/control_plane/deny_reason")
            deny_route.respond(json={"result": "Action denied: tool not recognized"})

            engine = PolicyEngine(opa_url="http://localhost:8181")
            decision = await engine.check(request)

        assert decision.allowed is False

    async def test_opa_allow_with_correlation_id(self):
        """Allowed decisions should preserve the request_id."""
        req_id = "corr-allow-123"
        request = PolicyRequest(
            agent_id=uuid4(),
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "CUST-001"},
            request_id=req_id,
        )

        async with respx.mock:
            route = respx.post("http://localhost:8181/v1/data/control_plane/allow")
            route.respond(json={"result": True})

            engine = PolicyEngine(opa_url="http://localhost:8181")
            decision = await engine.check(request)

        assert decision.allowed is True
        assert decision.request_id == req_id

    async def test_policy_request_correlation_id_passthrough(self):
        """The request_id field should be preserved in the decision."""
        req_id = "test-correlation-123"
        request = PolicyRequest(
            agent_id=uuid4(),
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "CUST-001"},
            request_id=req_id,
        )

        async with respx.mock:
            route = respx.post("http://localhost:8181/v1/data/control_plane/allow")
            route.respond(json={"result": True})

            engine = PolicyEngine(opa_url="http://localhost:8181")
            decision = await engine.check(request)

        assert decision.request_id == req_id


@pytest.mark.asyncio
class TestPolicyEngineEdgeCases:
    """Edge cases for the policy engine client."""

    async def test_engine_timeout_denies(self):
        """When OPA times out, policy should deny."""
        request = PolicyRequest(
            agent_id=uuid4(),
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "CUST-001"},
        )

        # Use a non-routable port to simulate timeout/failure
        engine = PolicyEngine(opa_url="http://localhost:19999")
        decision = await engine.check(request)

        assert decision.allowed is False

    async def test_engine_close_idempotent(self):
        """Calling close multiple times should not error."""
        engine = PolicyEngine(opa_url="http://localhost:8181")
        await engine.close()
        await engine.close()  # Second close should be safe
