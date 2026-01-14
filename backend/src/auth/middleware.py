"""Authentication middleware and FastAPI dependencies."""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.jwt import verify_token
from src.storage.database import User, get_session


# HTTPBearer extracts the token from the Authorization header
# auto_error=False means it won't raise an error if the header is missing
security = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> Optional[User]:
    """Get the current user if authenticated, None otherwise.

    Use this dependency when authentication is optional.

    Args:
        credentials: The Authorization header credentials (if present).
        session: Database session.

    Returns:
        The authenticated User if valid token provided, None otherwise.
    """
    if not credentials:
        return None

    user_id = verify_token(credentials.credentials, "access")
    if not user_id:
        return None

    result = await session.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    return result.scalar_one_or_none()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Get the current authenticated user, or raise 401.

    Use this dependency when authentication is required.

    Args:
        credentials: The Authorization header credentials.
        session: Database session.

    Returns:
        The authenticated User.

    Raises:
        HTTPException: 401 if not authenticated or token invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = verify_token(credentials.credentials, "access")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await session.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
