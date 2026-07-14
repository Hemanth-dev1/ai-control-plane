"""Event models for the Enterprise AI Control Plane event streaming."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of events produced by the system."""

    POLICY_DECISION = "policy.decision"
    EXECUTION_STEP = "execution.step"
    TOOL_INVOCATION = "tool.invocation"
    NOTIFICATION_OUTBOUND = "notification.outbound"
    AGENT_REGISTERED = "agent.registered"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"


class AuditEvent(BaseModel):
    """Generic audit event for compliance and observability."""

    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    source_service: str = Field(..., description="Which service emitted the event")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = Field(None, description="Trace/correlation ID")
    payload: dict[str, Any] = Field(default_factory=dict)
    agent_id: Optional[UUID] = None
    run_id: Optional[UUID] = None

    class Config:
        use_enum_values = True


class ExecutionStep(BaseModel):
    """A single step in an agent execution trace."""

    step_number: int
    step_type: str = Field(..., description="llm_call, tool_call, tool_result, policy_check, error")
    duration_ms: float = 0.0
    tokens_used: Optional[int] = None
    tool_name: Optional[str] = None
    tool_arguments: Optional[dict[str, Any]] = None
    tool_result: Optional[dict[str, Any]] = None
    policy_allowed: Optional[bool] = None
    llm_response: Optional[str] = None
    error: Optional[str] = None


class ExecutionEvent(BaseModel):
    """Event emitted at each step of an agent execution."""

    event_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    agent_id: UUID
    prompt: str = ""
    steps: list[ExecutionStep] = Field(default_factory=list)
    status: str = "running"  # running, completed, failed
    total_duration_ms: float = 0.0
    total_tokens_used: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None
