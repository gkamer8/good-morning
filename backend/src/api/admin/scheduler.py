"""Admin scheduler monitoring routes."""

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.template_config import templates
from src.storage.database import Briefing, Schedule, User, get_session


router = APIRouter()


@router.get("/scheduler")
async def admin_scheduler_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Admin scheduler monitoring page."""
    from . import is_authenticated
    from src.main import get_scheduler
    
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    scheduler = get_scheduler()

    # Get all schedules with user info
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    schedules_result = await session.execute(
        select(Schedule, User)
        .outerjoin(User, Schedule.user_id == User.id)
        .order_by(Schedule.user_id)
    )
    schedules_data = []
    for schedule, user in schedules_result.all():
        schedules_data.append({
            "user_id": schedule.user_id,
            "user_name": user.display_name if user else None,
            "user_email": user.email if user else None,
            "enabled": schedule.enabled,
            "time": f"{schedule.time_hour:02d}:{schedule.time_minute:02d}",
            "days": ", ".join(day_names[d] for d in sorted(schedule.days_of_week)),
            "timezone": schedule.timezone,
        })

    # Get scheduler jobs
    jobs = []
    next_run = None
    scheduler_running = scheduler is not None and scheduler.running

    if scheduler_running:
        for job in scheduler.get_jobs():
            job_next_run = job.next_run_time
            if job_next_run:
                next_run_str = job_next_run.strftime("%Y-%m-%d %H:%M:%S %Z")
                if next_run is None:
                    next_run = next_run_str
            else:
                next_run_str = "Not scheduled"

            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run_str,
                "trigger": str(job.trigger),
            })

    # Get recent briefings with user info
    result = await session.execute(
        select(Briefing, User)
        .outerjoin(User, Briefing.user_id == User.id)
        .order_by(Briefing.created_at.desc())
        .limit(20)
    )
    briefings_raw = result.all()

    briefings = []
    for b, user in briefings_raw:
        errors = b.generation_errors if b.generation_errors else []
        rendered = b.rendered_prompts if b.rendered_prompts else {}
        segments_meta = b.segments_metadata if b.segments_metadata else {}

        music_error = segments_meta.get("music_error")
        if music_error:
            errors = errors + [{
                "error_type": "Music Error",
                "segment": "music",
                "message": music_error,
                "timestamp": b.created_at.strftime("%Y-%m-%d %H:%M"),
            }]

        briefings.append({
            "id": b.id,
            "title": b.title,
            "created_at": b.created_at.strftime("%Y-%m-%d %H:%M"),
            "status": b.status,
            "duration": f"{int(b.duration_seconds // 60)}:{int(b.duration_seconds % 60):02d}" if b.duration_seconds else "-",
            "error_count": len(errors),
            "errors": errors,
            "has_prompts": bool(rendered),
            "rendered_prompts": rendered,
            "user_id": b.user_id,
            "user_name": user.display_name if user else None,
            "user_email": user.email if user else None,
        })

    return templates.TemplateResponse(
        request,
        "admin/scheduler.html",
        {
            "active_page": "admin-scheduler",
            "is_authenticated": True,
            "scheduler_running": scheduler_running,
            "schedules": schedules_data,
            "next_run": next_run,
            "jobs": jobs,
            "briefings": briefings,
            "last_checked": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
    )

