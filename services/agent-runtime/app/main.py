"""Agent runtime — runs the actual agent loop (LLM calls, tool-call parsing, re-invocation).

Endpoints:
- POST /run          — start a new agent run
- GET  /runs/{id}    — fetch run details (stored in memory for demo)
- GET  /health       — health check
- GET  /metrics      — Prometheus metrics
"""

from __future__ import annotations

import uuid
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
from starlette.responses import Response

from app.config import settings
from app.control_plane_client import ControlPlaneClient
from app.llm_client import LLMClient
from app.loop import AgentLoop

logger = structlog.get_logger(__name__)

# --- Prometheus metrics ---
REQUEST_LATENCY = Histogram(
    "agent_runtime_request_duration_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
)
RUN_COUNTER = Counter("agent_runtime_runs_total", "Total agent runs", ["status"])
TOKEN_USAGE = Counter("agent_runtime_tokens_total", "Total tokens used", [])

# --- In-memory run store (use DB in production) ---
run_store: dict[str, dict] = {}

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
    title="Agent Runtime",
    version="0.1.0",
    description="Runs AI agents with policy-enforced tool access",
)


@app.on_event("startup")
async def startup_event():
    setup_logging(settings.service_name, settings.log_level)
    setup_telemetry()
    FastAPIInstrumentor.instrument_app(app)
    logger.info("agent_runtime_started", host=settings.host, port=settings.port)


@app.middleware("http")
async def metrics_middleware(request, call_next):
    import time

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    REQUEST_LATENCY.labels(method=request.method, endpoint=request.url.path).observe(duration)
    return response


# --- Request/Response models ---
class RunRequest(BaseModel):
    agent_id: str
    prompt: str


class RunResponse(BaseModel):
    run_id: str
    status: str
    response: str | list | dict
    steps: list[dict]
    total_duration_ms: float
    total_tokens_used: int


# --- Endpoints ---

@app.get("/health")
async def health():
    return {"status": "healthy", "service": settings.service_name}


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")


@app.post("/run", response_model=RunResponse)
async def run_agent(request: RunRequest):
    """Start a new agent execution run."""
    agent_id = UUID(request.agent_id)

    llm_client = LLMClient()
    control_plane = ControlPlaneClient()
    loop = AgentLoop(
        agent_id=agent_id,
        llm_client=llm_client,
        control_plane=control_plane,
        tool_gateway_url=settings.tool_gateway_url,
    )

    logger.info(
        "run_started",
        run_id=str(loop.run_id),
        agent_id=str(agent_id),
        prompt=request.prompt[:100],
    )

    try:
        result = await loop.run(request.prompt)
        run_store[str(loop.run_id)] = result

        RUN_COUNTER.labels(status=result["status"]).inc()
        TOKEN_USAGE.inc(result.get("total_tokens_used", 0))

        return RunResponse(**result)
    except Exception as e:
        logger.error("run_failed", run_id=str(loop.run_id), error=str(e))
        RUN_COUNTER.labels(status="failed").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    """Fetch the full trace of a past run."""
    result = run_store.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return result
