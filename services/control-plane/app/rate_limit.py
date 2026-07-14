"""Rate limiting for the control plane — uses slowapi with a Redis backend."""

from __future__ import annotations

from slowapi import Limiter as SlowAPILimiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

# Use Redis backend if configured, otherwise fall back to in-memory
# For production, ensure REDIS_URL is set to a Redis instance
limiter = SlowAPILimiter(
    key_func=get_remote_address,
    default_limits=["100/hour"],
    storage_uri=settings.redis_url,
)

# Per-agent rate limit key function
def get_agent_rate_limit_key(request):
    """Extract the agent ID from the JWT token for per-agent rate limiting."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        from jose import jwt as jose_jwt

        try:
            token = auth_header[7:]
            payload = jose_jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            return payload.get("sub", get_remote_address(request))
        except Exception:
            return get_remote_address(request)
    return get_remote_address(request)
