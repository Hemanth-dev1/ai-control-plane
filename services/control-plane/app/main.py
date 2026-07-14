"""Control plane — identity, authorization, policy enforcement, rate limiting, agent registry.

Endpoints:
- POST /agents          — register a new agent
- GET  /agents/{id}     — fetch agent details
- POST /auth/token      — issue a JWT (OAuth2 client-credentials)
- POST /policy/check    — evaluate a policy request
- GET  /health          — health check
- GET  /metrics         — Prometheus metrics
"""

from __future__ import annotations

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Histogram, generate_latest
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from pydantic import BaseModel

from app.auth import (
    authenticate_agent,
    create_access_token,
    get_current_agent,
)
from app.config import settings
from app.db.database import get_db
from app.db.migrate import run_migrations_async
from app.policy import PolicyEngine
from app.rate_limit import limiter, get_agent_rate_limit_key
from app.registry import AgentRegistry, get_registry
from shared_schemas.agent import Agent, AgentRegistration, AgentTokenResponse
from shared_schemas.logging_config import setup_logging
from shared_schemas.policy import PolicyDecision, PolicyRequest


class AgentWithKey(BaseModel):
    """Agent response that includes the API key (only shown once)."""
    agent: Agent
    api_key: str

logger = structlog.get_logger(__name__)

# --- Prometheus metrics ---
REQUEST_LATENCY = Histogram(
    "control_plane_request_duration_seconds",
    "Request latency in seconds",
    ["method", "endpoint", "status_code"],
)
POLICY_DECISIONS = Counter(
    "control_plane_policy_decisions_total",
    "Total policy decisions",
    ["decision"],
)
AGENT_OPERATIONS = Counter(
    "control_plane_agent_operations_total",
    "Total agent CRUD operations",
    ["operation"],
)

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
    title="Enterprise AI Control Plane",
    version="0.1.0",
    description="Identity, authorization, policy enforcement, and agent registry",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# --- Event handler ---
@app.on_event("startup")
async def startup_event():
    setup_logging(settings.service_name, settings.log_level)
    setup_telemetry()
    FastAPIInstrumentor.instrument_app(app)
    await run_migrations_async()
    logger.info("control_plane_started", host=settings.host, port=settings.port)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning("rate_limit_exceeded", path=str(request.url))
    return Response(content="Rate limit exceeded", status_code=status.HTTP_429_TOO_MANY_REQUESTS)


# --- Middleware for metrics ---
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    import time

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
    ).observe(duration)
    return response


# --- Endpoints ---

@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Health check — verifies DB connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "service": settings.service_name}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unhealthy: {e}")


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type="text/plain")


@app.post("/auth/token", response_model=AgentTokenResponse)
async def issue_token(request: Request, db: AsyncSession = Depends(get_db)):
    """Issue a JWT for an agent (OAuth2 client-credentials flow).

    Expects form data: client_id (agent name) and client_secret (API key).
    """
    body = await request.form()
    client_id = body.get("client_id")
    client_secret = body.get("client_secret")

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_id and client_secret are required",
        )

    agent = await authenticate_agent(client_id, client_secret, db)
    scopes = [s.value for s in agent.allowed_scopes]
    access_token = create_access_token(agent.id, scopes)

    logger.info("token_issued", agent_id=str(agent.id), scopes=scopes)

    return AgentTokenResponse(access_token=access_token)


from pydantic import BaseModel


class AgentWithKey(BaseModel):
    """Agent response that includes the API key (only shown once)."""
    agent: Agent
    api_key: str


@app.post("/agents", response_model=AgentWithKey)
async def register_agent(
    registration: AgentRegistration,
    registry: AgentRegistry = Depends(get_registry),
):
    """Register a new agent."""
    import secrets

    api_key = f"ak_{secrets.token_urlsafe(32)}"
    agent = await registry.create_agent(registration, api_key)

    AGENT_OPERATIONS.labels(operation="create").inc()
    logger.info("agent_registered", agent_id=str(agent.id), name=agent.name)

    # Return the agent with the API key in the response (only time it's shown)
    return AgentWithKey(agent=agent, api_key=api_key)


@app.get("/agents/{agent_id}", response_model=Agent)
async def get_agent(
    agent_id: str,
    registry: AgentRegistry = Depends(get_registry),
    current_agent: Agent = Depends(get_current_agent),
):
    """Fetch agent details (requires authentication)."""
    from uuid import UUID

    agent = await registry.get_agent(UUID(agent_id))
    return agent


@app.post("/policy/check", response_model=PolicyDecision)
async def check_policy(
    request: PolicyRequest,
    current_agent: Agent = Depends(get_current_agent),
):
    """Check whether an agent action is allowed by policy."""
    engine = PolicyEngine()
    decision = await engine.check(request)

    POLICY_DECISIONS.labels(decision="allowed" if decision.allowed else "denied").inc()
    logger.info(
        "policy_check",
        agent_id=str(request.agent_id),
        tool_name=request.tool_name,
        allowed=decision.allowed,
        reason=decision.reason,
    )

    return decision
