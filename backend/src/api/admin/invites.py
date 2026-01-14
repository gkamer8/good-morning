"""Admin invite code management routes."""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.template_config import templates
from src.storage.database import AdminSettings, InviteCode, User, get_session


router = APIRouter()


@router.get("/invites")
async def admin_invites_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    success: str = None,
    error: str = None,
):
    """Admin invite code management page."""
    from . import is_authenticated
    
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    result = await session.execute(
        select(InviteCode).order_by(InviteCode.created_at.desc())
    )
    invites = result.scalars().all()

    invites_data = []
    for invite in invites:
        user_email = None
        if invite.used_by_user_id:
            user_result = await session.execute(
                select(User).where(User.id == invite.used_by_user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                user_email = user.email or user.display_name or f"User #{user.id}"

        invites_data.append({
            "id": invite.id,
            "code": invite.code,
            "created_at": invite.created_at.strftime("%Y-%m-%d %H:%M"),
            "max_uses": invite.max_uses,
            "use_count": invite.use_count,
            "expires_at": invite.expires_at.strftime("%Y-%m-%d %H:%M") if invite.expires_at else None,
            "note": invite.note,
            "used_by": user_email,
            "is_valid": invite.use_count < invite.max_uses and (
                invite.expires_at is None or invite.expires_at > datetime.now()
            ),
        })

    test_mode_result = await session.execute(
        select(AdminSettings).where(AdminSettings.key == "invite_test_mode_email")
    )
    test_mode_setting = test_mode_result.scalar_one_or_none()
    invite_test_mode_enabled = test_mode_setting is not None and test_mode_setting.value
    invite_test_mode_email = test_mode_setting.value if test_mode_setting else "gkamer@outlook.com"

    return templates.TemplateResponse(
        request,
        "admin/invites.html",
        {
            "active_page": "admin-invites",
            "is_authenticated": True,
            "invites": invites_data,
            "success": success,
            "error": error,
            "invite_test_mode_enabled": invite_test_mode_enabled,
            "invite_test_mode_email": invite_test_mode_email,
        },
    )


@router.post("/invites/create")
async def admin_create_invite(
    request: Request,
    note: str = Form(default=""),
    max_uses: int = Form(default=1),
    expires_days: int = Form(default=0),
    session: AsyncSession = Depends(get_session),
):
    """Create a new invite code."""
    from . import is_authenticated
    
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    code = secrets.token_urlsafe(6).upper()[:8]

    expires_at = None
    if expires_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

    invite = InviteCode(
        code=code,
        max_uses=max_uses,
        expires_at=expires_at,
        note=note or None,
    )
    session.add(invite)
    await session.commit()

    return RedirectResponse(
        url=f"/admin/invites?success=Created+invite+code:+{code}",
        status_code=302,
    )


@router.post("/invites/{invite_id}/delete")
async def admin_delete_invite(
    request: Request,
    invite_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete an invite code."""
    from . import is_authenticated
    
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    result = await session.execute(
        select(InviteCode).where(InviteCode.id == invite_id)
    )
    invite = result.scalar_one_or_none()

    if not invite:
        return RedirectResponse(
            url="/admin/invites?error=Invite+code+not+found",
            status_code=302,
        )

    code = invite.code
    await session.delete(invite)
    await session.commit()

    return RedirectResponse(
        url=f"/admin/invites?success=Deleted+invite+code:+{code}",
        status_code=302,
    )


@router.post("/invites/test-mode/enable")
async def admin_enable_invite_test_mode(
    request: Request,
    email: str = Form(default="gkamer@outlook.com"),
    session: AsyncSession = Depends(get_session),
):
    """Enable invite test mode for a specific email."""
    from . import is_authenticated
    
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    result = await session.execute(
        select(AdminSettings).where(AdminSettings.key == "invite_test_mode_email")
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = email
    else:
        setting = AdminSettings(key="invite_test_mode_email", value=email)
        session.add(setting)

    await session.commit()

    return RedirectResponse(
        url=f"/admin/invites?success=Invite+test+mode+enabled+for+{email}",
        status_code=302,
    )


@router.post("/invites/test-mode/disable")
async def admin_disable_invite_test_mode(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Disable invite test mode."""
    from . import is_authenticated
    
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    result = await session.execute(
        select(AdminSettings).where(AdminSettings.key == "invite_test_mode_email")
    )
    setting = result.scalar_one_or_none()

    if setting:
        await session.delete(setting)
        await session.commit()

    return RedirectResponse(
        url="/admin/invites?success=Invite+test+mode+disabled",
        status_code=302,
    )

