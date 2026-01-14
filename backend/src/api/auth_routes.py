"""Authentication API endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.apple import verify_apple_identity_token
from src.auth.jwt import TokenPair, create_token_pair, verify_token
from src.config import get_settings
from src.storage.database import AdminSettings, InviteCode, Schedule, User, UserSettings, get_session


router = APIRouter(prefix="/auth", tags=["auth"])


# === Request/Response Models ===


class AppleSignInRequest(BaseModel):
    """Request body for Apple Sign-In."""

    identity_token: str  # JWT from Apple Sign-In
    user_name: Optional[str] = None  # Display name (only provided on first sign-in)
    invite_code: Optional[str] = None  # Required for new users


class RefreshRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str


class AuthResponse(BaseModel):
    """Response for successful authentication."""

    user_id: int
    display_name: Optional[str]
    email: Optional[str]
    tokens: TokenPair
    is_new_user: bool


class UserInfoResponse(BaseModel):
    """Response for user info endpoint."""

    user_id: int
    display_name: Optional[str]
    email: Optional[str]
    created_at: datetime


# === Endpoints ===


@router.post("/apple", response_model=AuthResponse)
async def apple_sign_in(
    request: AppleSignInRequest,
    session: AsyncSession = Depends(get_session),
):
    """Sign in with Apple.

    For existing users: validates the Apple identity token and returns new tokens.
    For new users: requires a valid invite code to create an account.
    """
    settings = get_settings()

    # Verify the Apple identity token
    claims = await verify_apple_identity_token(
        request.identity_token,
        settings.apple_bundle_ids,
    )

    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Apple identity token",
        )

    # Check if user already exists
    result = await session.execute(select(User).where(User.apple_id == claims.sub))
    user = result.scalar_one_or_none()
    is_new_user = False

    # Check if invite test mode is enabled for this user's email
    test_mode_enabled = False
    if claims.email:
        test_mode_result = await session.execute(
            select(AdminSettings).where(AdminSettings.key == "invite_test_mode_email")
        )
        test_mode_setting = test_mode_result.scalar_one_or_none()
        if test_mode_setting and test_mode_setting.value:
            # Case-insensitive email comparison
            test_mode_enabled = claims.email.lower() == test_mode_setting.value.lower()

    # If user exists and test mode is NOT enabled, normal login
    if user and not test_mode_enabled:
        # Existing user - update last login
        user.last_login_at = datetime.now(timezone.utc)
        # Update email if we got one and don't have it yet
        if claims.email and not user.email:
            user.email = claims.email
        await session.commit()
    else:
        # New user OR test mode is enabled - require invite code
        if not request.invite_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invite code required for new users",
            )

        # Validate invite code
        result = await session.execute(
            select(InviteCode).where(InviteCode.code == request.invite_code.upper())
        )
        invite = result.scalar_one_or_none()

        if not invite:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid invite code",
            )

        if invite.use_count >= invite.max_uses:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invite code has been fully used",
            )

        if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invite code has expired",
            )

        # Mark invite code as used (do this regardless of test mode)
        invite.use_count += 1

        if test_mode_enabled and user:
            # Test mode: user already exists, just use them (don't create new)
            # Update last login time
            user.last_login_at = datetime.now(timezone.utc)
            invite.used_by_user_id = user.id
            await session.commit()
            # Mark as NOT a new user since we're reusing the account
            is_new_user = False
        else:
            # Actually a new user - create account
            user = User(
                apple_id=claims.sub,
                email=claims.email,
                display_name=request.user_name,
                last_login_at=datetime.now(timezone.utc),
            )
            session.add(user)
            await session.flush()  # Get user.id assigned

            invite.used_by_user_id = user.id

            # Create default settings for the new user
            default_settings = UserSettings(user_id=user.id)
            session.add(default_settings)

            # Create default schedule for the new user
            default_schedule = Schedule(user_id=user.id)
            session.add(default_schedule)

            await session.commit()
            is_new_user = True

    # Generate tokens
    tokens = create_token_pair(user.id)

    return AuthResponse(
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        tokens=tokens,
        is_new_user=is_new_user,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh_tokens(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_session),
):
    """Refresh access token using a refresh token.

    Returns a new token pair if the refresh token is valid.
    """
    user_id = verify_token(request.refresh_token, "refresh")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Verify user still exists and is active
    result = await session.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return create_token_pair(user.id)


@router.post("/logout")
async def logout():
    """Logout the current user.

    Since JWT tokens are stateless, this endpoint just returns success.
    The client should discard its stored tokens.
    """
    return {"status": "logged_out"}


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    session: AsyncSession = Depends(get_session),
    credentials: Optional[str] = Depends(lambda: None),  # Will be replaced by actual auth
):
    """Get information about the current authenticated user.

    This endpoint requires authentication and returns user profile information.
    """
    from src.auth.middleware import get_current_user
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

    # Note: This endpoint will be properly secured after we update routes.py
    # For now, it's a placeholder that shows the intended structure.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="This endpoint requires the auth middleware to be integrated",
    )
