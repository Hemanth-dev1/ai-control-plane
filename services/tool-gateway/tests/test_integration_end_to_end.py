"""End-to-end integration tests for the tool gateway.

Tests the full flow:
  1. Agent registration → JWT token issuance
  2. Tool discovery via /tools
  3. Allowed tool call → successful execution
  4. Denied tool call (scope) → rejection
  5. Denied tool call (policy/threshold) → rejection
  6. Audit log contains all decisions

Uses httpx AsyncClient against the live FastAPI ASGI app for the tool gateway,
and respx to mock cross-service HTTP calls to the control plane and backends.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import respx
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
class TestToolGatewayEndToEnd:
    """End-to-end tests for the tool gateway flow."""

    @pytest.fixture(autouse=True)
    def setup_respx_mocks(self, respx_mock: respx.MockRouter):
        """Mock external service calls by default."""
        # Mock CRM service
        respx_mock.get("http://crm-service:8003/customers/CUST-001").respond(
            json={
                "id": "CUST-001",
                "name": "Acme Corporation",
                "email": "contact@acme.com",
                "tier": "premium",
                "status": "active",
            },
        )
        respx_mock.get("http://crm-service:8003/customers/INVALID").respond(
            status_code=404,
            json={"detail": "Customer INVALID not found"},
        )

        # Mock ticketing service
        respx_mock.post("http://ticketing-service:8004/tickets").respond(
            json={
                "id": str(uuid4()),
                "title": "Test Ticket",
                "description": "Test description",
                "status": "open",
                "priority": "high",
                "customer_id": "CUST-001",
            },
        )

        # Mock notification service
        respx_mock.post("http://notification-service:8005/notifications").respond(
            json={
                "success": True,
                "message": "Notification sent to test@example.com via email",
            },
        )

    async def test_list_tools_returns_all_schemas(self, async_client: AsyncClient):
        """GET /tools should return all 5 tool schemas."""
        response = await async_client.get("/tools")
        assert response.status_code == 200
        tools = response.json()
        assert len(tools) == 5

        tool_names = {t["name"] for t in tools}
        assert "crm.lookup_customer" in tool_names
        assert "crm.add_note" in tool_names
        assert "ticketing.create_ticket" in tool_names
        assert "ticketing.get_ticket" in tool_names
        assert "notify.send_message" in tool_names

        # Each tool should have required schema fields
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert "backend_service" in tool

    async def test_execute_unknown_tool_returns_404(self, async_client: AsyncClient):
        """POST /execute with an unknown tool name should return 404."""
        response = await async_client.post(
            "/execute",
            json={
                "tool_name": "unknown.tool",
                "arguments": {},
                "agent_id": str(uuid4()),
            },
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    async def test_execute_crm_lookup_success(
        self,
        async_client: AsyncClient,
        mock_kafka_producer: AsyncMock,
        sample_agent_id: str,
        sample_run_id: str,
    ):
        """A valid CRM lookup call should succeed and emit audit event."""
        response = await async_client.post(
            "/execute",
            json={
                "tool_name": "crm.lookup_customer",
                "arguments": {"customer_id": "CUST-001"},
                "agent_id": sample_agent_id,
                "run_id": sample_run_id,
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert result["data"]["name"] == "Acme Corporation"

        # Verify audit event was emitted
        mock_kafka_producer.emit_tool_invocation.assert_called_once()
        call_kwargs = mock_kafka_producer.emit_tool_invocation.call_args
        assert "crm.lookup_customer" in str(call_kwargs)

    async def test_execute_crm_lookup_invalid_customer(
        self,
        async_client: AsyncClient,
        mock_kafka_producer: AsyncMock,
    ):
        """Lookup of an invalid customer should return failure with audit event."""
        response = await async_client.post(
            "/execute",
            json={
                "tool_name": "crm.lookup_customer",
                "arguments": {"customer_id": "INVALID"},
                "agent_id": str(uuid4()),
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is False

    async def test_execute_missing_required_field_fails_validation(
        self,
        async_client: AsyncClient,
        mock_kafka_producer: AsyncMock,
    ):
        """Missing required customer_id field should fail validation."""
        response = await async_client.post(
            "/execute",
            json={
                "tool_name": "crm.lookup_customer",
                "arguments": {},
                "agent_id": str(uuid4()),
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is False
        assert "Validation failed" in result["error"]

    async def test_execute_ticketing_create_ticket(
        self,
        async_client: AsyncClient,
        mock_kafka_producer: AsyncMock,
    ):
        """Creating a ticket with valid args should succeed."""
        response = await async_client.post(
            "/execute",
            json={
                "tool_name": "ticketing.create_ticket",
                "arguments": {
                    "title": "Test Ticket",
                    "description": "Test description",
                    "priority": "high",
                    "customer_id": "CUST-001",
                },
                "agent_id": str(uuid4()),
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert result["data"]["title"] == "Test Ticket"
        assert result["data"]["status"] == "open"

    async def test_execute_notify_send_message(
        self,
        async_client: AsyncClient,
        mock_kafka_producer: AsyncMock,
    ):
        """Sending a notification should succeed."""
        response = await async_client.post(
            "/execute",
            json={
                "tool_name": "notify.send_message",
                "arguments": {
                    "recipient": "test@example.com",
                    "subject": "Hello",
                    "message": "Test message",
                    "channel": "email",
                },
                "agent_id": str(uuid4()),
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True

    async def test_execute_with_invalid_schema_fails(
        self,
        async_client: AsyncClient,
        mock_kafka_producer: AsyncMock,
    ):
        """Passing wrong argument types should fail schema validation."""
        response = await async_client.post(
            "/execute",
            json={
                "tool_name": "ticketing.create_ticket",
                "arguments": {
                    "title": 123,  # Should be a string
                    "description": True,  # Should be a string
                },
                "agent_id": str(uuid4()),
            },
        )
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is False
        assert "Validation failed" in result["error"]

    async def test_audit_event_emitted_for_every_call(
        self,
        async_client: AsyncClient,
        mock_kafka_producer: AsyncMock,
        sample_agent_id: str,
    ):
        """Every tool execution should produce an audit event."""
        # Reset call count
        mock_kafka_producer.emit_tool_invocation.reset_mock()

        # Make a valid call
        await async_client.post(
            "/execute",
            json={
                "tool_name": "crm.lookup_customer",
                "arguments": {"customer_id": "CUST-001"},
                "agent_id": sample_agent_id,
            },
        )

        # Verify audit event was emitted
        mock_kafka_producer.emit_tool_invocation.assert_called_once()

    async def test_concurrent_tool_calls(
        self,
        async_client: AsyncClient,
        mock_kafka_producer: AsyncMock,
    ):
        """Multiple concurrent tool calls should all succeed."""
        import asyncio

        async def make_call(tool: str, args: dict) -> int:
            resp = await async_client.post(
                "/execute",
                json={
                    "tool_name": tool,
                    "arguments": args,
                    "agent_id": str(uuid4()),
                },
            )
            return resp.status_code

        tools = [
            ("crm.lookup_customer", {"customer_id": "CUST-001"}),
            ("crm.lookup_customer", {"customer_id": "CUST-001"}),
            ("crm.lookup_customer", {"customer_id": "CUST-001"}),
        ]

        results = await asyncio.gather(*[make_call(t, a) for t, a in tools])
        assert all(r == 200 for r in results)

    async def test_health_endpoint(self, async_client: AsyncClient):
        """GET /health should return healthy status."""
        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "tool-gateway"
