"""Settings API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import DEFAULT_SEGMENT_ORDER, SettingsResponse, SettingsUpdate
from src.audio.tts import VOICES
from src.auth.middleware import get_current_user
from src.config import get_settings
from src.storage.database import User, UserSettings, get_session


router = APIRouter()
settings = get_settings()


@router.get("/settings", response_model=SettingsResponse)
async def get_settings_endpoint(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get current user settings."""
    result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        user_settings = UserSettings(
            user_id=user.id,
            voice_key="chatterbox_timmy",
            voice_style="energetic",
            voice_speed=1.1,
        )
        session.add(user_settings)
        await session.commit()
        await session.refresh(user_settings)

    return SettingsResponse(
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


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    update: SettingsUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update user settings."""
    result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    update_data = update.model_dump(exclude_unset=True)

    if "briefing_length" in update_data:
        print(f"[Settings] Updating briefing_length: {user_settings.briefing_length!r} -> {update_data['briefing_length']!r}")

    for field, value in update_data.items():
        if field == "sports_teams":
            user_settings.sports_teams = [t.model_dump() if hasattr(t, "model_dump") else t for t in value]
        elif field == "weather_locations":
            user_settings.weather_locations = [loc.model_dump() if hasattr(loc, "model_dump") else loc for loc in value]
        elif field == "voice_key":
            # Validate voice_key exists
            if value not in VOICES:
                raise HTTPException(status_code=400, detail=f"Unknown voice_key: {value}")
            user_settings.voice_key = value
        elif field == "news_topics":
            user_settings.news_topics = value
        elif field == "news_sources":
            user_settings.news_sources = value
        elif field == "sports_leagues":
            user_settings.sports_leagues = value
        elif field == "fun_segments":
            user_settings.fun_segments = value
        elif field == "briefing_length":
            user_settings.briefing_length = value
        elif field == "include_intro_music":
            user_settings.include_intro_music = value
        elif field == "include_transitions":
            user_settings.include_transitions = value
        elif field == "news_exclusions":
            user_settings.news_exclusions = value
        elif field == "voice_style":
            user_settings.voice_style = value
        elif field == "voice_speed":
            user_settings.voice_speed = value
        elif field == "segment_order":
            user_settings.segment_order = value
        elif field == "include_music":
            user_settings.include_music = value
        elif field == "writing_style":
            user_settings.writing_style = value
        elif field == "timezone":
            user_settings.timezone = value
        elif field == "deep_dive_enabled":
            user_settings.deep_dive_enabled = value

    await session.commit()
    await session.refresh(user_settings)

    return SettingsResponse(
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
