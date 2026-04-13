"""
JWT helpers â€” centralized token generation and validation for WebSocket authentication.

Provides:
  - PyJWT-based token creation with configurable expiration
  - Safe validation with logging of failures
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import jwt
from jwt import ExpiredSignatureError, PyJWTError

from redis_client import get_redis_client

logger = logging.getLogger("insightgraph.auth")

JWT_SECRET = os.getenv("JWT_SECRET", "insightgraph-jwt-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_SECONDS = int(os.getenv("JWT_EXPIRATION_SECONDS", "3600"))
REFRESH_TOKEN_TTL_SECONDS = int(os.getenv("JWT_REFRESH_TTL_SECONDS", "86400"))

_redis_client = get_redis_client()


def generate_jwt(
    user_id: str,
    roles: Optional[List[str]] = None,
    expires_in: Optional[int] = None,
) -> str:
    """
    Generate a signed JWT for the given user.
    """
    expiration = datetime.utcnow() + timedelta(seconds=expires_in or JWT_EXPIRATION_SECONDS)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "roles": roles or [],
        "exp": expiration,
        "iat": datetime.utcnow(),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def validate_jwt(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate a JWT and return the decoded claims.

    Returns None if the token is invalid or expired.
    """
    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require_sub": True},
        )
        return claims
    except ExpiredSignatureError:
        logger.debug("JWT expired")
    except PyJWTError as exc:
        logger.debug("JWT validation failed: %s", exc)
    return None


async def create_refresh_token(user_id: str, roles: Optional[List[str]] = None) -> str:
    """Generate a refresh token and persist it in Redis."""

    token = secrets.token_urlsafe(40)
    payload = json.dumps({"user_id": user_id, "roles": roles or []})
    success = await _redis_client.set(f"refresh:{token}", payload, ex=REFRESH_TOKEN_TTL_SECONDS)
    if not success:
        logger.warning("Refresh token for %s could not be persisted", user_id)
    return token


async def consume_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    """Validate and consume a refresh token (one-time use)."""

    key = f"refresh:{token}"
    payload = await _redis_client.get(key)
    if not payload:
        return None

    await _redis_client.delete(key)
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Refresh payload for %s was corrupted", token)
        return None
