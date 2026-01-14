"""Schedule API endpoints."""

from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import ScheduleResponse, ScheduleUpdate
from src.auth.middleware import get_current_user
from src.scheduler import create_scheduled_briefing_for_user
from src.storage.database import Schedule, User, UserSettings, get_session


router = APIRouter()


@router.get("/schedule", response_model=ScheduleResponse)
async def get_schedule(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get the current generation schedule."""
    result = await session.execute(
        select(Schedule).where(Schedule.user_id == user.id)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        schedule = Schedule(user_id=user.id)
        session.add(schedule)
        await session.commit()
        await session.refresh(schedule)

    return ScheduleResponse(
        id=schedule.id,
        enabled=schedule.enabled,
        days_of_week=schedule.days_of_week,
        time_hour=schedule.time_hour,
        time_minute=schedule.time_minute,
        timezone=schedule.timezone,
        next_run=None,
    )


@router.put("/schedule", response_model=ScheduleResponse)
async def update_schedule(
    update: ScheduleUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update the generation schedule."""
    result = await session.execute(
        select(Schedule).where(Schedule.user_id == user.id)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    update_data = update.model_dump(exclude_unset=True)
    if "enabled" in update_data:
        schedule.enabled = update_data["enabled"]
    if "days_of_week" in update_data:
        schedule.days_of_week = update_data["days_of_week"]
    if "time_hour" in update_data:
        schedule.time_hour = update_data["time_hour"]
    if "time_minute" in update_data:
        schedule.time_minute = update_data["time_minute"]
    if "timezone" in update_data:
        schedule.timezone = update_data["timezone"]

    if "timezone" in update_data:
        settings_result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        user_settings = settings_result.scalar_one_or_none()
        if user_settings:
            user_settings.timezone = schedule.timezone

    await session.commit()
    await session.refresh(schedule)

    # Update the running scheduler with new settings for this user
    from src.main import get_scheduler
    scheduler = get_scheduler()
    job_id = f"morning_briefing_user_{user.id}"

    if scheduler and scheduler.running:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

        if schedule.enabled:
            days_str = ",".join(str(d) for d in schedule.days_of_week)
            trigger = CronTrigger(
                hour=schedule.time_hour,
                minute=schedule.time_minute,
                day_of_week=days_str,
                timezone=ZoneInfo(schedule.timezone),
            )
            scheduler.add_job(
                create_scheduled_briefing_for_user,
                trigger,
                args=[user.id],
                id=job_id,
                name=f"Morning Briefing - {user.email or user.display_name or f'User #{user.id}'}",
                replace_existing=True,
            )

    return ScheduleResponse(
        id=schedule.id,
        enabled=schedule.enabled,
        days_of_week=schedule.days_of_week,
        time_hour=schedule.time_hour,
        time_minute=schedule.time_minute,
        timezone=schedule.timezone,
        next_run=None,
    )

