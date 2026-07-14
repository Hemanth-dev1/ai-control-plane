"""Tool gateway — mediates all tool calls to backend systems with schema validation and audit logging.

Endpoints:
- GET  /tools        — list all available tool schemas
- POST /execute      — execute a tool invocation
- GET  /health       — health check
- GET  /metrics      — Prometheus metrics
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest
from shared_schemas.logging_config import setup_logging
from shared_schemas.tool import ToolSchema
from starlette.responses import Response

from app.audit import AuditProducer
from app.backends.crm_client import CRMClient
from app.backends.notification_client import NotificationClient
from app.backends.ticketing_client import TicketingClient
from app.config import settings
from app.mcp_server import create_mcp_server
from app.schema_validator import SchemaValidator

logger = structlog.get_logger(__name__)

# --- Prometheus metrics ---
REQUEST_LATENCY = Histogram(
    "tool_gateway_request_duration_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
)
TOOL_CALL_COUNTER = Counter(
    "tool_gateway_tool_calls_total",
    "Total tool calls",
    ["tool_name", "success"],
)

# --- Tool definitions ---
CRM_LOOKUP_TOOL = ToolSchema(
    name="crm.lookup_customer",
    description="Look up a customer by their ID in the CRM system",
    input_schema={
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "The customer's unique identifier",
            },
        },
        "required": ["customer_id"],
    },
    backend_service="crm-service",
)

CRM_ADD_NOTE_TOOL = ToolSchema(
    name="crm.add_note",
    description="Add a note to a customer's record",
    input_schema={
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "description": "The customer's unique identifier"},
            "note": {"type": "string", "description": "The note content to add"},
        },
        "required": ["customer_id", "note"],
    },
    backend_service="crm-service",
)

TICKETING_CREATE_TOOL = ToolSchema(
    name="ticketing.create_ticket",
    description="Create a new support ticket",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Ticket title"},
            "description": {"type": "string", "description": "Detailed description"},
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": "Ticket priority",
            },
            "customer_id": {"type": "string", "description": "Associated customer ID"},
        },
        "required": ["title", "description"],
    },
    backend_service="ticketing-service",
)

TICKETING_GET_TOOL = ToolSchema(
    name="ticketing.get_ticket",
    description="Get details of a support ticket by ID",
    input_schema={
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string", "description": "The ticket's unique identifier"},
        },
        "required": ["ticket_id"],
    },
    backend_service="ticketing-service",
)

NOTIFY_SEND_TOOL = ToolSchema(
    name="notify.send_message",
    description="Send a notification message to a recipient",
    input_schema={
        "type": "object",
        "properties": {
            "recipient": {"type": "string", "description": "Recipient email or identifier"},
            "subject": {"type": "string", "description": "Message subject"},
            "message": {"type": "string", "description": "Message body content"},
            "channel": {
                "type": "string",
                "enum": ["email", "sms", "slack"],
                "description": "Delivery channel",
            },
        },
        "required": ["recipient", "subject", "message"],
    },
    backend_service="notification-service",
)

AVAILABLE_TOOLS: dict[str, ToolSchema] = {
    CRM_LOOKUP_TOOL.name: CRM_LOOKUP_TOOL,
    CRM_ADD_NOTE_TOOL.name: CRM_ADD_NOTE_TOOL,
    TICKETING_CREATE_TOOL.name: TICKETING_CREATE_TOOL,
    TICKETING_GET_TOOL.name: TICKETING_GET_TOOL,
    NOTIFY_SEND_TOOL.name: NOTIFY_SEND_TOOL,
}

# --- MCP Server setup ---
mcp_server = None


def get_mcp_app():
    """Get or create the mounted MCP server ASGI app."""
    global mcp_server
    if mcp_server is None:
        fastmcp = create_mcp_server(
            crm_client=crm_client,
            ticketing_client=ticketing_client,
            notification_client=notification_client,
            schema_validator=schema_validator,
            audit_producer=audit_producer,
            available_tools=AVAILABLE_TOOLS,
        )
        mcp_server = fastmcp.app
    return mcp_server


# --- OpenTelemetry setup ---
def setup_telemetry():
    resource = Resource.create({"service.name": settings.service_name})
    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
    span_processor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(span_processor)
    trace.set_tracer_provider(provider)


# --- FastAPI app ---
app = FastAPI(
    title="Tool Gateway",
    version="0.1.0",
    description="MCP-compatible tool gateway with schema validation and audit logging",
)

# Global instances
crm_client = CRMClient()
ticketing_client = TicketingClient()
notification_client = NotificationClient()
schema_validator = SchemaValidator()
audit_producer = AuditProducer()

# Mount MCP server at /mcp — exposes SSE endpoint for MCP-compatible clients
app.mount("/mcp", get_mcp_app())

# Backend router
BACKEND_ROUTER = {
    "crm.lookup_customer": crm_client.lookup_customer,
    "crm.add_note": crm_client.add_note,
    "ticketing.create_ticket": ticketing_client.create_ticket,
    "ticketing.get_ticket": ticketing_client.get_ticket,
    "notify.send_message": notification_client.send_message,
}


@app.on_event("startup")
async def startup_event():
    setup_logging(settings.service_name, settings.log_level)
    setup_telemetry()
    FastAPIInstrumentor.instrument_app(app)
    await audit_producer.connect()
    logger.info("tool_gateway_started", host=settings.host, port=settings.port)


@app.on_event("shutdown")
async def shutdown_event():
    await audit_producer.close()


@app.middleware("http")
async def metrics_middleware(request, call_next):
    import time

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    REQUEST_LATENCY.labels(method=request.method, endpoint=request.url.path).observe(duration)
    return response


# --- Request/Response models ---
class ExecuteRequest(BaseModel):
    tool_name: str
    arguments: dict = {}
    agent_id: str | None = None
    run_id: str | None = None


# --- Endpoints ---

@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name}


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")


@app.get("/tools")
async def list_tools():
    """List all available tool schemas."""
    return [tool.model_dump(mode="json") for tool in AVAILABLE_TOOLS.values()]


@app.post("/execute")
async def execute_tool(request: ExecuteRequest):
    """Execute a tool invocation with schema validation."""
    tool_schema = AVAILABLE_TOOLS.get(request.tool_name)
    if tool_schema is None:
        raise HTTPException(status_code=404, detail=f"Tool '{request.tool_name}' not found")

    # Validate arguments against schema
    is_valid, error = schema_validator.validate(tool_schema, request.arguments)
    if not is_valid:
        TOOL_CALL_COUNTER.labels(tool_name=request.tool_name, success="false").inc()
        await audit_producer.emit_tool_invocation(
            tool_name=request.tool_name,
            arguments=request.arguments,
            agent_id=UUID(request.agent_id) if request.agent_id else UUID(int=0),
            run_id=UUID(request.run_id) if request.run_id else None,
            success=False,
            error=error,
        )
        return {"success": False, "error": error}

    # Execute the tool
    handler = BACKEND_ROUTER.get(request.tool_name)
    if handler is None:
        raise HTTPException(status_code=500, detail=f"No handler for tool '{request.tool_name}'")

    import time
    start = time.time()

    try:
        result = await handler(**request.arguments)
        duration_ms = (time.time() - start) * 1000

        TOOL_CALL_COUNTER.labels(
            tool_name=request.tool_name,
            success="true" if result.get("success") else "false",
        ).inc()

        await audit_producer.emit_tool_invocation(
            tool_name=request.tool_name,
            arguments=request.arguments,
            agent_id=UUID(request.agent_id) if request.agent_id else UUID(int=0),
            run_id=UUID(request.run_id) if request.run_id else None,
            success=result.get("success", False),
            result=result.get("data"),
            error=result.get("error"),
            duration_ms=duration_ms,
        )

        return result
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        logger.error("tool_execution_failed", tool=request.tool_name, error=str(e))

        TOOL_CALL_COUNTER.labels(tool_name=request.tool_name, success="false").inc()

        await audit_producer.emit_tool_invocation(
            tool_name=request.tool_name,
            arguments=request.arguments,
            agent_id=UUID(request.agent_id) if request.agent_id else UUID(int=0),
            run_id=UUID(request.run_id) if request.run_id else None,
            success=False,
            error=str(e),
            duration_ms=duration_ms,
        )

        return {"success": False, "error": str(e)}
