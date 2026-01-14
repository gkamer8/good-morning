"""JWT token handling for authentication."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from pydantic import BaseModel

from src.config import get_settings


class TokenPair(BaseModel):
    """A pair of access and refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


def create_access_token(user_id: int) -> str:
    """Create an access token for the given user.

    Args:
        user_id: The user's database ID.

    Returns:
        A signed JWT access token.
    """
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_access_token_expire_hours)
    payload = {
        "sub": str(user_id),
        "exp": expires,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def create_refresh_token(user_id: int) -> str:
    """Create a refresh token for the given user.

    Args:
        user_id: The user's database ID.

    Returns:
        A signed JWT refresh token.
    """
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "exp": expires,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def create_token_pair(user_id: int) -> TokenPair:
    """Create both access and refresh tokens for a user.

    Args:
        user_id: The user's database ID.

    Returns:
        A TokenPair containing both tokens.
    """
    settings = get_settings()
    return TokenPair(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        expires_in=settings.jwt_access_token_expire_hours * 3600,
    )


def verify_token(token: str, expected_type: str = "access") -> Optional[int]:
    """Verify a JWT token and return the user ID if valid.

    Args:
        token: The JWT token to verify.
        expected_type: Expected token type ("access" or "refresh").

    Returns:
        The user_id if the token is valid, None otherwise.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])

        # Verify token type
        if payload.get("type") != expected_type:
            return None

        # Extract user_id
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None

        return int(user_id_str)
    except (jwt.PyJWTError, ValueError):
        return None
