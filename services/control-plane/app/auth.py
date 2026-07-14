"""JWT authentication and OAuth2 client-credentials flow for the control plane."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.db.models import AgentModel
from shared_schemas.agent import Agent, AgentStatus

security_scheme = HTTPBearer(auto_error=False)

# In-memory token blacklist (use Redis in production)
_token_blacklist: set[str] = set()


def hash_api_key(api_key: str) -> str:
    """Hash an API key using bcrypt."""
    return _bcrypt.hashpw(api_key.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_api_key(plain_api_key: str, hashed_api_key: str) -> bool:
    """Verify a plain API key against a bcrypt hash."""
    return _bcrypt.checkpw(plain_api_key.encode("utf-8"), hashed_api_key.encode("utf-8"))


def create_access_token(
    agent_id: UUID,
    scopes: list[str],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token for an agent."""
    if expires_delta is None:
        expires_delta = timedelta(seconds=settings.jwt_expiration_seconds)

    now = datetime.utcnow()
    payload = {
        "sub": str(agent_id),
        "scopes": scopes,
        "iat": now,
        "exp": now + expires_delta,
        "iss": settings.service_name,
        "token_type": "access_token",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    if token in _token_blacklist:
        raise JWTError("Token has been revoked")

    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    return payload


def revoke_token(token: str) -> None:
    """Revoke a token by adding it to the blacklist."""
    _token_blacklist.add(token)


async def authenticate_agent(
    client_id: str,
    client_secret: str,
    db: AsyncSession,
) -> Agent:
    """Authenticate an agent using client credentials (OAuth2 client-credentials flow)."""
    result = await db.execute(select(AgentModel).where(AgentModel.name == client_id))
    agent_model = result.scalar_one_or_none()

    if agent_model is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials",
        )

    if agent_model.status != AgentStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent account is not active",
        )

    if not verify_api_key(client_secret, agent_model.api_key_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials",
        )

    return agent_model.to_schema()


async def get_current_agent(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    """FastAPI dependency: extract and validate the current agent from the JWT."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )

    agent_id = payload.get("sub")
    if agent_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
        )

    result = await db.execute(select(AgentModel).where(AgentModel.id == UUID(agent_id)))
    agent_model = result.scalar_one_or_none()

    if agent_model is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent not found",
        )

    if agent_model.status != AgentStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent account is not active",
        )

    return agent_model.to_schema()
