"""Agent registry — CRUD operations for agent registrations."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_api_key
from app.db.database import get_db
from app.db.models import AgentModel
from shared_schemas.agent import Agent, AgentRegistration, AgentStatus


class AgentRegistry:
    """CRUD operations for the agent registry."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_agent(
        self,
        registration: AgentRegistration,
        api_key: str,
    ) -> Agent:
        """Register a new agent and return the agent record."""
        api_key_hash = hash_api_key(api_key)

        agent_model = AgentModel(
            name=registration.name,
            description=registration.description,
            allowed_scopes=[s.value for s in registration.allowed_scopes],
            api_key_hash=api_key_hash,
            status=AgentStatus.ACTIVE,
            max_tool_budget=registration.max_tool_budget,
        )

        self.db.add(agent_model)
        await self.db.flush()
        await self.db.refresh(agent_model)

        return agent_model.to_schema()

    async def get_agent(self, agent_id: UUID) -> Agent:
        """Fetch an agent by ID."""
        result = await self.db.execute(select(AgentModel).where(AgentModel.id == agent_id))
        agent_model = result.scalar_one_or_none()

        if agent_model is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        return agent_model.to_schema()

    async def list_agents(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Agent]:
        """List all registered agents with pagination."""
        result = await self.db.execute(
            select(AgentModel)
            .offset(skip)
            .limit(limit)
            .order_by(AgentModel.created_at.desc())
        )
        agents = result.scalars().all()
        return [agent.to_schema() for agent in agents]

    async def update_agent(
        self,
        agent_id: UUID,
        registration: AgentRegistration,
    ) -> Agent:
        """Update an existing agent's registration."""
        result = await self.db.execute(select(AgentModel).where(AgentModel.id == agent_id))
        agent_model = result.scalar_one_or_none()

        if agent_model is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        agent_model.name = registration.name
        agent_model.description = registration.description
        agent_model.allowed_scopes = [s.value for s in registration.allowed_scopes]
        agent_model.max_tool_budget = registration.max_tool_budget

        await self.db.flush()
        await self.db.refresh(agent_model)

        return agent_model.to_schema()

    async def delete_agent(self, agent_id: UUID) -> None:
        """Soft-delete an agent by setting status to INACTIVE."""
        result = await self.db.execute(select(AgentModel).where(AgentModel.id == agent_id))
        agent_model = result.scalar_one_or_none()

        if agent_model is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        agent_model.status = AgentStatus.INACTIVE
        await self.db.flush()

    async def suspend_agent(self, agent_id: UUID) -> Agent:
        """Suspend an agent."""
        result = await self.db.execute(select(AgentModel).where(AgentModel.id == agent_id))
        agent_model = result.scalar_one_or_none()

        if agent_model is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )

        agent_model.status = AgentStatus.SUSPENDED
        await self.db.flush()
        await self.db.refresh(agent_model)

        return agent_model.to_schema()


async def get_registry(db: AsyncSession = Depends(get_db)) -> AgentRegistry:
    """Dependency to get an AgentRegistry instance."""
    return AgentRegistry(db)
