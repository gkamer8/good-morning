"""Scheduler for automatic briefing generation."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from src.agents.orchestrator import generate_briefing_task
from src.storage.database import Briefing, Schedule, UserSettings, async_session, init_db
from src.utils.timezone import get_user_now


async def create_scheduled_briefing():
    """Create a briefing based on the schedule."""
    # Get user timezone for the title
    async with async_session() as session:
        result = await session.execute(select(UserSettings).limit(1))
        user_settings = result.scalar_one_or_none()
        user_tz = getattr(user_settings, 'timezone', None) or "America/New_York"

    user_now = get_user_now(user_tz)
    print(f"[{user_now}] Starting scheduled briefing generation...")

    # Create a new briefing record
    async with async_session() as session:
        briefing = Briefing(
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
        await generate_briefing_task(briefing_id=briefing_id)
        print(f"[{get_user_now(user_tz)}] Scheduled briefing {briefing_id} completed successfully!")
    except Exception as e:
        print(f"[{get_user_now(user_tz)}] Scheduled briefing {briefing_id} failed: {e}")


async def setup_scheduler():
    """Set up the scheduler based on user settings."""
    # Initialize database
    await init_db()

    # Get schedule and user settings
    async with async_session() as session:
        result = await session.execute(select(Schedule).limit(1))
        schedule = result.scalar_one_or_none()

        result = await session.execute(select(UserSettings).limit(1))
        user_settings = result.scalar_one_or_none()

    if not schedule or not schedule.enabled:
        print("Scheduler is disabled or not configured.")
        return None

    # Use UserSettings.timezone as primary, fall back to Schedule.timezone
    user_tz = (
        getattr(user_settings, 'timezone', None) or
        schedule.timezone or
        "America/New_York"
    )

    # Create scheduler
    scheduler = AsyncIOScheduler()

    # Convert days of week to cron format (0=Monday in our DB, 0=Monday in APScheduler)
    days_str = ",".join(str(d) for d in schedule.days_of_week)

    # Add the job
    trigger = CronTrigger(
        hour=schedule.time_hour,
        minute=schedule.time_minute,
        day_of_week=days_str,
        timezone=ZoneInfo(user_tz),
    )

    scheduler.add_job(
        create_scheduled_briefing,
        trigger,
        id="morning_briefing",
        name="Morning Briefing Generation",
        replace_existing=True,
    )

    print(f"Scheduler configured: {schedule.time_hour:02d}:{schedule.time_minute:02d} "
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
        print("Scheduler not started (disabled or not configured).")


if __name__ == "__main__":
    asyncio.run(main())
