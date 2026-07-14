"""Tool models for the Enterprise AI Control Plane."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, JsonValue


class ToolParameter(BaseModel):
    """Schema for a single tool parameter."""

    name: str = Field(..., description="Parameter name")
    type: str = Field(..., description="JSON Schema type")
    description: Optional[str] = Field(None, description="Parameter description")
    required: bool = False


class ToolSchema(BaseModel):
    """Full schema for a tool exposed by the gateway."""

    name: str = Field(..., description="Fully-qualified tool name, e.g. 'crm.lookup_customer'")
    description: Optional[str] = Field(None, description="What the tool does")
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for tool inputs",
    )
    backend_service: str = Field(..., description="Which backend system handles this tool")


class ToolInvocation(BaseModel):
    """Record of a tool being invoked."""

    invocation_id: UUID = Field(default_factory=uuid4)
    tool_name: str
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    agent_id: UUID
    run_id: Optional[UUID] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ToolResult(BaseModel):
    """Result of a tool invocation."""

    invocation_id: UUID
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
