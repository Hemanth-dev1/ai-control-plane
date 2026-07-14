"""Agent models for the Enterprise AI Control Plane."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    """Status of an agent registration."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class AgentScope(str, Enum):
    """Scopes/tools an agent is allowed to use."""

    CRM_LOOKUP_CUSTOMER = "crm.lookup_customer"
    CRM_ADD_NOTE = "crm.add_note"
    TICKETING_CREATE_TICKET = "ticketing.create_ticket"
    TICKETING_GET_TICKET = "ticketing.get_ticket"
    NOTIFY_SEND_MESSAGE = "notify.send_message"


class AgentRegistration(BaseModel):
    """Payload for registering a new agent."""

    name: str = Field(..., min_length=1, max_length=256, description="Human-readable agent name")
    description: Optional[str] = Field(None, max_length=2048, description="Description of the agent's purpose")
    allowed_scopes: list[AgentScope] = Field(
        default_factory=list,
        description="List of tool scopes this agent is permitted to use",
    )
    max_tool_budget: Optional[int] = Field(
        None,
        description="Maximum number of tool invocations allowed per session",
        ge=1,
    )


class Agent(BaseModel):
    """Complete agent record as stored and returned."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    description: Optional[str] = None
    allowed_scopes: list[AgentScope] = Field(default_factory=list)
    api_key_hash: str = Field(..., description="Bcrypt hash of the agent's API key")
    status: AgentStatus = AgentStatus.ACTIVE
    max_tool_budget: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True


class AgentTokenResponse(BaseModel):
    """Response from the token endpoint."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
