"""SQLAlchemy ORM models for the control plane."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase

from shared_schemas.agent import AgentScope, AgentStatus


class Base(DeclarativeBase):
    pass


class AgentModel(Base):
    """Database model for agent registrations."""

    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(256), nullable=False, index=True)
    description = Column(Text, nullable=True)
    allowed_scopes = Column(ARRAY(String), nullable=False, default=list)
    api_key_hash = Column(String(256), nullable=False)
    status = Column(Enum(AgentStatus), nullable=False, default=AgentStatus.ACTIVE)
    max_tool_budget = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_schema(self):
        from shared_schemas.agent import Agent

        return Agent(
            id=self.id,
            name=self.name,
            description=self.description,
            allowed_scopes=[AgentScope(s) for s in (self.allowed_scopes or [])],
            api_key_hash=self.api_key_hash,
            status=self.status,
            max_tool_budget=self.max_tool_budget,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
