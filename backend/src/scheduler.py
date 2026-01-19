"""Scheduler for automatic briefing generation."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from src.briefing.orchestrator import generate_briefing_task
from src.storage.database import Briefing, Schedule, User, UserSettings, async_session, init_db
from src.utils.timezone import get_user_now


async def create_scheduled_briefing_for_user(user_id: int):
    """Create a briefing for a specific user based on their schedule."""
    # Get user's timezone
    async with async_session() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        user_settings = result.scalar_one_or_none()
        user_tz = (user_settings.timezone if user_settings else None) or "America/New_York"

        # Get user info for logging
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        user_name = user.email or user.display_name or f"User #{user_id}" if user else f"User #{user_id}"

    user_now = get_user_now(user_tz)
    print(f"[{user_now}] Starting scheduled briefing generation for {user_name}...")

    # Create a new briefing record for this user
    async with async_session() as session:
        briefing = Briefing(
            user_id=user_id,
            title=f"Morning Briefing - {user_now.strftime('%B %d, %Y')}",
            duration_seconds=0,
            audio_filename="",
            script={},
            segments_metadata={},
            status="pending",
        )
        session.add(briefing)
        await session.commit()
        await session.refresh(briefing)
        briefing_id = briefing.id

    # Generate the briefing
    try:
        await generate_briefing_task(briefing_id=briefing_id, user_id=user_id)
        print(f"[{get_user_now(user_tz)}] Scheduled briefing {briefing_id} for {user_name} completed successfully!")
    except Exception as e:
        print(f"[{get_user_now(user_tz)}] Scheduled briefing {briefing_id} for {user_name} failed: {e}")


async def setup_scheduler():
    """Set up the scheduler based on all users' schedules."""
    # Initialize database
    await init_db()

    # Get all enabled schedules with user info
    async with async_session() as session:
        result = await session.execute(
            select(Schedule, User, UserSettings)
            .outerjoin(User, Schedule.user_id == User.id)
            .outerjoin(UserSettings, Schedule.user_id == UserSettings.user_id)
            .where(Schedule.enabled == True)
        )
        schedules_with_users = result.all()

    if not schedules_with_users:
        print("No enabled schedules found.")
        return None

    # Create scheduler
    scheduler = AsyncIOScheduler()

    # Add a job for each user's schedule
    for schedule, user, user_settings in schedules_with_users:
        # Skip schedules without user_id (legacy data)
        if not schedule.user_id:
            print(f"Skipping schedule {schedule.id} - no user_id (legacy)")
            continue

        # Use UserSettings.timezone as primary, fall back to Schedule.timezone
        user_tz = (
            user_settings.timezone if user_settings else None
        ) or schedule.timezone or "America/New_York"

        # Convert days of week to cron format
        days_str = ",".join(str(d) for d in schedule.days_of_week)

        # Create trigger for this user
        trigger = CronTrigger(
            hour=schedule.time_hour,
            minute=schedule.time_minute,
            day_of_week=days_str,
            timezone=ZoneInfo(user_tz),
        )

        # User identifier for job naming
        user_name = user.email or user.display_name or f"user_{schedule.user_id}" if user else f"user_{schedule.user_id}"
        job_id = f"morning_briefing_user_{schedule.user_id}"

        # Add the job for this user
        scheduler.add_job(
            create_scheduled_briefing_for_user,
            trigger,
            args=[schedule.user_id],
            id=job_id,
            name=f"Morning Briefing - {user_name}",
            replace_existing=True,
        )

        print(f"Scheduler configured for {user_name}: {schedule.time_hour:02d}:{schedule.time_minute:02d} "
              f"on days {schedule.days_of_week} ({user_tz})")

    return scheduler


async def main():
    """Main entry point for the scheduler service."""
    print("Starting Morning Drive Scheduler...")

    scheduler = await setup_scheduler()

    if scheduler:
        scheduler.start()
        print("Scheduler started. Press Ctrl+C to exit.")

        try:
            # Keep the scheduler running
            while True:
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            print("\nShutting down scheduler...")
            scheduler.shutdown()
    else:
        print("Scheduler not started (no enabled schedules).")


if __name__ == "__main__":
    asyncio.run(main())
