"""Policy models for the Enterprise AI Control Plane."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PolicyRequest(BaseModel):
    """Request to check whether an agent action is allowed."""

    agent_id: UUID = Field(..., description="The agent requesting the action")
    tool_name: str = Field(..., description="Fully-qualified tool name, e.g. 'crm.lookup_customer'")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments to evaluate")
    request_id: Optional[str] = Field(None, description="Correlation ID for tracing")


class PolicyDecision(BaseModel):
    """Decision returned by the policy engine."""

    allowed: bool = Field(..., description="Whether the action is permitted")
    reason: str = Field(..., description="Human-readable justification for the decision")
    decision_id: str = Field(default="", description="Unique ID for this decision (for audit)")
    request_id: Optional[str] = Field(None, description="Correlation ID from the request")
