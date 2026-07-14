"""MCP server implementation for the tool gateway.

Defines tools as MCP-compatible handlers using the official `mcp` Python SDK.
Each handler wraps schema validation, backend execution, and Kafka audit logging.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from mcp.server.fastmcp import FastMCP
from opentelemetry import trace
from prometheus_client import Counter as PromCounter

from app.audit import AuditProducer
from app.backends.crm_client import CRMClient
from app.backends.notification_client import NotificationClient
from app.backends.ticketing_client import TicketingClient
from app.schema_validator import SchemaValidator
from shared_schemas.tool import ToolSchema

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

# Prometheus counter — shared naming convention with main.py
TOOL_CALL_COUNTER = PromCounter(
    "tool_gateway_mcp_tool_calls_total",
    "Total MCP tool calls",
    ["tool_name", "success"],
)


def create_mcp_server(
    crm_client: CRMClient,
    ticketing_client: TicketingClient,
    notification_client: NotificationClient,
    schema_validator: SchemaValidator,
    audit_producer: AuditProducer,
    available_tools: dict[str, ToolSchema] | None = None,
) -> FastMCP:
    """Create and configure the MCP server with all tool definitions.

    Args:
        crm_client: Client for the CRM backend service.
        ticketing_client: Client for the ticketing backend service.
        notification_client: Client for the notification backend service.
        schema_validator: Validator for tool input arguments.
        audit_producer: Kafka producer for audit events.
        available_tools: Tool schemas dict for validation (injected to avoid circular imports).

    Returns:
        A configured FastMCP instance with all tools registered.
    """
    mcp = FastMCP("tool-gateway")

    _tool_schemas = available_tools or {}

    # ── Tool: crm.lookup_customer ───────────────────────────────────────

    @mcp.tool(name="crm.lookup_customer")
    async def crm_lookup_customer(customer_id: str) -> str:
        """Look up a customer by their ID in the CRM system.

        Args:
            customer_id: The customer's unique identifier (e.g., CUST-001).
        """
        with tracer.start_as_current_span("mcp_tool.crm.lookup_customer") as span:
            span.set_attribute("customer_id", customer_id)

            tool_name = "crm.lookup_customer"
            arguments = {"customer_id": customer_id}
            tool_schema = _tool_schemas.get(tool_name)
            invocation_id = str(uuid.uuid4())

            # Schema validation
            if tool_schema:
                is_valid, error = schema_validator.validate(tool_schema, arguments)
                if not is_valid:
                    TOOL_CALL_COUNTER.labels(tool_name=tool_name, success="false").inc()
                    await _emit_audit(audit_producer, tool_name, arguments, False, error=error)
                    return _error_result(error)

            # Execute
            start = time.time()
            try:
                result = await crm_client.lookup_customer(customer_id)
                duration_ms = (time.time() - start) * 1000

                TOOL_CALL_COUNTER.labels(
                    tool_name=tool_name,
                    success="true" if result.get("success") else "false",
                ).inc()

                await _emit_audit(
                    audit_producer, tool_name, arguments, result.get("success", False),
                    result=result.get("data"), error=result.get("error"), duration_ms=duration_ms,
                )

                if result.get("success"):
                    return str(result.get("data", {}))
                return _error_result(result.get("error", "Unknown error"))
            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                TOOL_CALL_COUNTER.labels(tool_name=tool_name, success="false").inc()
                await _emit_audit(
                    audit_producer, tool_name, arguments, False, error=str(e), duration_ms=duration_ms,
                )
                return _error_result(str(e))

    # ── Tool: ticketing.create_ticket ────────────────────────────────────

    @mcp.tool(name="ticketing.create_ticket")
    async def ticketing_create_ticket(
        title: str,
        description: str,
        priority: str = "medium",
        customer_id: str | None = None,
    ) -> str:
        """Create a new support ticket in the ticketing system.

        Args:
            title: Ticket title (required).
            description: Detailed description of the issue (required).
            priority: Ticket priority level (low, medium, high, critical).
            customer_id: Associated customer ID if applicable.
        """
        with tracer.start_as_current_span("mcp_tool.ticketing.create_ticket") as span:
            span.set_attribute("title", title)

            tool_name = "ticketing.create_ticket"
            arguments = {"title": title, "description": description, "priority": priority}
            if customer_id:
                arguments["customer_id"] = customer_id
            tool_schema = _tool_schemas.get(tool_name)

            if tool_schema:
                is_valid, error = schema_validator.validate(tool_schema, arguments)
                if not is_valid:
                    TOOL_CALL_COUNTER.labels(tool_name=tool_name, success="false").inc()
                    await _emit_audit(audit_producer, tool_name, arguments, False, error=error)
                    return _error_result(error)

            start = time.time()
            try:
                result = await ticketing_client.create_ticket(
                    title=title, description=description,
                    priority=priority, customer_id=customer_id,
                )
                duration_ms = (time.time() - start) * 1000

                TOOL_CALL_COUNTER.labels(
                    tool_name=tool_name,
                    success="true" if result.get("success") else "false",
                ).inc()

                await _emit_audit(
                    audit_producer, tool_name, arguments, result.get("success", False),
                    result=result.get("data"), error=result.get("error"), duration_ms=duration_ms,
                )

                if result.get("success"):
                    return str(result.get("data", {}))
                return _error_result(result.get("error", "Unknown error"))
            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                TOOL_CALL_COUNTER.labels(tool_name=tool_name, success="false").inc()
                await _emit_audit(
                    audit_producer, tool_name, arguments, False, error=str(e), duration_ms=duration_ms,
                )
                return _error_result(str(e))

    # ── Tool: notify.send_message ────────────────────────────────────────

    @mcp.tool(name="notify.send_message")
    async def notify_send_message(
        recipient: str,
        subject: str,
        message: str,
        channel: str = "email",
    ) -> str:
        """Send a notification message to a recipient.

        Args:
            recipient: Recipient email address or identifier.
            subject: Message subject line.
            message: Message body content.
            channel: Delivery channel (email, sms, slack).
        """
        with tracer.start_as_current_span("mcp_tool.notify.send_message") as span:
            span.set_attribute("recipient", recipient)

            tool_name = "notify.send_message"
            arguments = {
                "recipient": recipient, "subject": subject,
                "message": message, "channel": channel,
            }
            tool_schema = _tool_schemas.get(tool_name)

            if tool_schema:
                is_valid, error = schema_validator.validate(tool_schema, arguments)
                if not is_valid:
                    TOOL_CALL_COUNTER.labels(tool_name=tool_name, success="false").inc()
                    await _emit_audit(audit_producer, tool_name, arguments, False, error=error)
                    return _error_result(error)

            start = time.time()
            try:
                result = await notification_client.send_message(
                    recipient=recipient, subject=subject,
                    message=message, channel=channel,
                )
                duration_ms = (time.time() - start) * 1000

                TOOL_CALL_COUNTER.labels(
                    tool_name=tool_name,
                    success="true" if result.get("success") else "false",
                ).inc()

                await _emit_audit(
                    audit_producer, tool_name, arguments, result.get("success", False),
                    result=result.get("data"), error=result.get("error"), duration_ms=duration_ms,
                )

                if result.get("success"):
                    return str(result.get("data", result.get("message", "Notification sent")))
                return _error_result(result.get("error", "Unknown error"))
            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                TOOL_CALL_COUNTER.labels(tool_name=tool_name, success="false").inc()
                await _emit_audit(
                    audit_producer, tool_name, arguments, False, error=str(e), duration_ms=duration_ms,
                )
                return _error_result(str(e))

    return mcp


# ── Internal helpers ────────────────────────────────────────────────────────

async def _emit_audit(
    producer: AuditProducer,
    tool_name: str,
    arguments: dict[str, Any],
    success: bool,
    result: Any = None,
    error: str | None = None,
    duration_ms: float = 0.0,
) -> None:
    """Emit an audit event for a tool invocation."""
    await producer.emit_tool_invocation(
        tool_name=tool_name,
        arguments=arguments,
        agent_id=uuid.UUID(int=0),
        run_id=None,
        success=success,
        result=result,
        error=error,
        duration_ms=duration_ms,
    )


def _error_result(message: str | None) -> str:
    """Format an error result string."""
    return f"Error: {message}" if message else "Error: Unknown error"
