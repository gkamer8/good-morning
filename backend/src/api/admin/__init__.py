"""Admin interface routes for Morning Drive."""

import secrets
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.api.template_config import templates
from src.config import get_settings

from .health import router as health_router
from .invites import router as invites_router
from .music import router as music_router
from .previews import router as previews_router
from .scheduler import router as scheduler_router
from .users import router as users_router


settings = get_settings()

# Simple session storage (in production, use proper session management)
_admin_sessions: set[str] = set()


def verify_admin_password(password: str) -> bool:
    """Verify the admin password."""
    return password == settings.admin_password


def generate_session_token() -> str:
    """Generate a simple session token."""
    return secrets.token_urlsafe(32)


def get_session_token(request: Request) -> Optional[str]:
    """Get session token from cookie."""
    return request.cookies.get("admin_session")


def is_authenticated(request: Request) -> bool:
    """Check if the request is authenticated."""
    token = get_session_token(request)
    return token is not None and token in _admin_sessions


def add_session(token: str) -> None:
    """Add a session token."""
    _admin_sessions.add(token)


def remove_session(token: str) -> None:
    """Remove a session token."""
    _admin_sessions.discard(token)


# Main admin router
router = APIRouter()


@router.get("/")
async def admin_index(request: Request):
    """Admin index - redirect to login or music page."""
    if is_authenticated(request):
        return RedirectResponse(url="/admin/music", status_code=302)
    return RedirectResponse(url="/admin/login", status_code=302)


@router.get("/login")
async def admin_login_page(request: Request, error: str = None):
    """Admin login page."""
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {"error": error, "is_authenticated": False},
    )


@router.post("/login")
async def admin_login(password: str = Form(...)):
    """Handle admin login."""
    if verify_admin_password(password):
        token = generate_session_token()
        add_session(token)
        response = RedirectResponse(url="/admin/music", status_code=302)
        response.set_cookie(
            key="admin_session",
            value=token,
            httponly=True,
            max_age=86400,  # 24 hours
            samesite="lax"
        )
        return response
    return RedirectResponse(url="/admin/login?error=Invalid+password", status_code=302)


@router.get("/logout")
async def admin_logout(request: Request):
    """Handle admin logout."""
    token = get_session_token(request)
    if token:
        remove_session(token)
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie("admin_session")
    return response


# Include sub-routers
router.include_router(health_router)
router.include_router(invites_router)
router.include_router(music_router)
router.include_router(previews_router)
router.include_router(scheduler_router)
router.include_router(users_router)

