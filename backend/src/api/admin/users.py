"""Admin user management routes."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import DEFAULT_SEGMENT_ORDER, SettingsResponse
from src.api.template_config import templates
from src.storage.database import Briefing, Schedule, User, UserSettings, get_session


router = APIRouter()


@router.get("/users")
async def admin_users_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Admin user management page."""
    from . import is_authenticated
    
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    result = await session.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    users_data = []
    for user in users:
        settings_result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        user_settings = settings_result.scalar_one_or_none()

        schedule_result = await session.execute(
            select(Schedule).where(Schedule.user_id == user.id)
        )
        user_schedule = schedule_result.scalar_one_or_none()

        briefings_result = await session.execute(
            select(Briefing).where(Briefing.user_id == user.id)
        )
        briefings_count = len(briefings_result.scalars().all())

        schedule_dict = {}
        if user_schedule:
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            schedule_dict = {
                "enabled": user_schedule.enabled,
                "time": f"{user_schedule.time_hour:02d}:{user_schedule.time_minute:02d}",
                "days": ", ".join(day_names[d] for d in sorted(user_schedule.days_of_week)),
                "timezone": user_schedule.timezone,
            }

        users_data.append({
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M"),
            "last_login_at": user.last_login_at.strftime("%Y-%m-%d %H:%M") if user.last_login_at else None,
            "is_active": user.is_active,
            "has_settings": user_settings is not None,
            "schedule": schedule_dict,
            "briefings_count": briefings_count,
        })

    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "active_page": "admin-users",
            "is_authenticated": True,
            "users": users_data,
        },
    )


@router.get("/api/users/{user_id}/settings")
async def admin_get_user_settings(
    request: Request,
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get settings for a specific user (admin API)."""
    from . import is_authenticated
    
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        return JSONResponse({"error": "Settings not found"}, status_code=404)

    response = SettingsResponse(
        news_topics=user_settings.news_topics,
        news_sources=user_settings.news_sources,
        sports_teams=user_settings.sports_teams,
        sports_leagues=user_settings.sports_leagues,
        weather_locations=user_settings.weather_locations,
        fun_segments=user_settings.fun_segments,
        briefing_length=user_settings.briefing_length,
        include_intro_music=user_settings.include_intro_music,
        include_transitions=user_settings.include_transitions,
        news_exclusions=user_settings.news_exclusions or [],
        voice_key=user_settings.voice_key,
        voice_style=user_settings.voice_style,
        voice_speed=user_settings.voice_speed,
        segment_order=user_settings.segment_order or DEFAULT_SEGMENT_ORDER,
        include_music=user_settings.include_music or False,
        writing_style=user_settings.writing_style or "good_morning_america",
        timezone=user_settings.timezone or "America/New_York",
        deep_dive_enabled=user_settings.deep_dive_enabled,
        updated_at=user_settings.updated_at,
    )

    return JSONResponse(response.model_dump(mode='json'))

