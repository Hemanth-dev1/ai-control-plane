"""Tests for shared Pydantic v2 models — validation, serialization, defaults."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from shared_schemas.agent import Agent, AgentRegistration, AgentScope, AgentStatus
from shared_schemas.events import AuditEvent, EventType, ExecutionEvent, ExecutionStep
from shared_schemas.policy import PolicyDecision, PolicyRequest
from shared_schemas.tool import ToolInvocation, ToolResult, ToolSchema


class TestAgentModels:
    def test_agent_registration_valid(self):
        reg = AgentRegistration(
            name="test-agent",
            description="A test agent",
            allowed_scopes=[AgentScope.CRM_LOOKUP_CUSTOMER],
        )
        assert reg.name == "test-agent"
        assert AgentScope.CRM_LOOKUP_CUSTOMER in reg.allowed_scopes

    def test_agent_registration_empty_name_fails(self):
        with pytest.raises(ValidationError):
            AgentRegistration(name="")

    def test_agent_registration_default_scopes(self):
        reg = AgentRegistration(name="test-agent")
        assert reg.allowed_scopes == []

    def test_agent_default_status(self):
        agent = Agent(name="test-agent", api_key_hash="hash")
        assert agent.status == AgentStatus.ACTIVE
        assert isinstance(agent.id, UUID)

    def test_agent_serialization(self):
        agent = Agent(name="test", api_key_hash="hash")
        data = agent.model_dump(mode="json")
        assert data["name"] == "test"
        assert data["status"] == "active"

    def test_agent_scope_values(self):
        assert AgentScope.CRM_LOOKUP_CUSTOMER.value == "crm.lookup_customer"
        assert AgentScope.NOTIFY_SEND_MESSAGE.value == "notify.send_message"


class TestPolicyModels:
    def test_policy_request_valid(self):
        req = PolicyRequest(
            agent_id=UUID("00000000-0000-0000-0000-000000000001"),
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "CUST-001"},
        )
        assert req.tool_name == "crm.lookup_customer"

    def test_policy_decision_allowed(self):
        decision = PolicyDecision(allowed=True, reason="OK", decision_id="d1")
        assert decision.allowed is True
        assert decision.reason == "OK"

    def test_policy_decision_denied(self):
        decision = PolicyDecision(allowed=False, reason="Not authorized", decision_id="d2")
        assert decision.allowed is False

    def test_policy_decision_defaults(self):
        decision = PolicyDecision(allowed=True, reason="OK")
        assert isinstance(decision.decision_id, str)
        assert decision.decision_id == ""


class TestToolModels:
    def test_tool_schema_valid(self):
        schema = ToolSchema(
            name="crm.lookup_customer",
            description="Look up a customer",
            input_schema={
                "type": "object",
                "properties": {"customer_id": {"type": "string"}},
                "required": ["customer_id"],
            },
            backend_service="crm-service",
        )
        assert schema.name == "crm.lookup_customer"
        assert "customer_id" in str(schema.input_schema)

    def test_tool_invocation(self):
        inv = ToolInvocation(
            tool_name="crm.lookup_customer",
            arguments={"customer_id": "CUST-001"},
            agent_id=UUID("00000000-0000-0000-0000-000000000001"),
        )
        assert isinstance(inv.invocation_id, UUID)

    def test_tool_result_success(self):
        result = ToolResult(
            invocation_id=UUID("00000000-0000-0000-0000-000000000001"),
            success=True,
            data={"name": "Acme Corp"},
        )
        assert result.success is True
        assert result.data["name"] == "Acme Corp"

    def test_tool_result_error(self):
        result = ToolResult(
            invocation_id=UUID("00000000-0000-0000-0000-000000000001"),
            success=False,
            error="Customer not found",
        )
        assert result.success is False
        assert result.error == "Customer not found"


class TestEventModels:
    def test_audit_event(self):
        event = AuditEvent(
            event_type=EventType.TOOL_INVOCATION,
            source_service="tool-gateway",
            payload={"tool_name": "crm.lookup_customer", "success": True},
        )
        assert isinstance(event.event_id, UUID)
        assert event.event_type == EventType.TOOL_INVOCATION

    def test_audit_event_serialization(self):
        event = AuditEvent(
            event_type=EventType.POLICY_DECISION,
            source_service="control-plane",
        )
        data = event.model_dump(mode="json")
        assert data["event_type"] == "policy.decision"
        assert data["source_service"] == "control-plane"

    def test_execution_step(self):
        step = ExecutionStep(
            step_number=1,
            step_type="llm_call",
            duration_ms=1500.0,
            tokens_used=500,
        )
        assert step.step_number == 1
        assert step.tokens_used == 500

    def test_execution_step_with_tool(self):
        step = ExecutionStep(
            step_number=2,
            step_type="tool_call",
            tool_name="crm.lookup_customer",
            tool_arguments={"customer_id": "CUST-001"},
            policy_allowed=True,
        )
        assert step.tool_name == "crm.lookup_customer"
        assert step.policy_allowed is True

    def test_execution_event(self):
        event = ExecutionEvent(
            run_id=UUID("00000000-0000-0000-0000-000000000001"),
            agent_id=UUID("00000000-0000-0000-0000-000000000002"),
            prompt="Test prompt",
        )
        assert event.status == "running"
        assert len(event.steps) == 0
        assert event.total_tokens_used == 0
