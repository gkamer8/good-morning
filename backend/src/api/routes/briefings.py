"""Briefing API endpoints."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.orchestrator import generate_briefing_task
from src.api.schemas import (
    BriefingCreate,
    BriefingListResponse,
    BriefingResponse,
    BriefingSegment,
    BriefingStatus,
    GenerationError,
    GenerationStatus,
    IN_PROGRESS_STATUSES,
    PendingAction,
    STATUS_PROGRESS,
)
from src.auth.middleware import get_current_user
from src.config import get_settings
from src.storage.database import Briefing, User, UserSettings, get_session
from src.utils.timezone import get_user_now


router = APIRouter()
settings = get_settings()


@router.post("/briefings/generate", response_model=GenerationStatus)
async def generate_briefing(
    request: BriefingCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Trigger generation of a new morning briefing."""
    result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = result.scalar_one_or_none()
    user_tz = (user_settings.timezone if user_settings else None) or "America/New_York"
    user_now = get_user_now(user_tz)

    briefing = Briefing(
        user_id=user.id,
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

    background_tasks.add_task(
        generate_briefing_task,
        briefing_id=briefing.id,
        user_id=user.id,
        override_length=request.override_length,
        override_topics=request.override_topics,
    )

    return GenerationStatus(
        briefing_id=briefing.id,
        status="pending",
        progress_percent=0,
        current_step="Starting generation...",
    )


@router.get("/briefings", response_model=BriefingListResponse)
async def list_briefings(
    limit: int = 10,
    offset: int = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all available briefings for the current user."""
    completed_statuses = ["completed", "completed_with_warnings"]
    result = await session.execute(
        select(Briefing)
        .where(Briefing.user_id == user.id)
        .where(Briefing.status.in_(completed_statuses))
        .order_by(Briefing.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    briefings = result.scalars().all()

    count_result = await session.execute(
        select(Briefing)
        .where(Briefing.user_id == user.id)
        .where(Briefing.status.in_(completed_statuses))
    )
    total = len(count_result.scalars().all())

    return BriefingListResponse(
        briefings=[
            BriefingResponse(
                id=b.id,
                created_at=b.created_at,
                title=b.title,
                duration_seconds=b.duration_seconds,
                audio_url=f"/audio/{b.audio_filename}",
                status=b.status,
                segments=[
                    BriefingSegment(**seg) for seg in b.segments_metadata.get("segments", [])
                ],
            )
            for b in briefings
        ],
        total=total,
    )


@router.get("/briefings/{briefing_id}", response_model=BriefingResponse)
async def get_briefing(
    briefing_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific briefing by ID."""
    result = await session.execute(
        select(Briefing).where(Briefing.id == briefing_id, Briefing.user_id == user.id)
    )
    briefing = result.scalar_one_or_none()

    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    return BriefingResponse(
        id=briefing.id,
        created_at=briefing.created_at,
        title=briefing.title,
        duration_seconds=briefing.duration_seconds,
        audio_url=f"/audio/{briefing.audio_filename}",
        status=briefing.status,
        segments=[
            BriefingSegment(**seg) for seg in briefing.segments_metadata.get("segments", [])
        ],
    )


@router.get("/briefings/{briefing_id}/status", response_model=GenerationStatus)
async def get_briefing_status(
    briefing_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get the generation status of a briefing."""
    result = await session.execute(
        select(Briefing).where(Briefing.id == briefing_id, Briefing.user_id == user.id)
    )
    briefing = result.scalar_one_or_none()

    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    try:
        status_enum = BriefingStatus(briefing.status)
        progress, step = STATUS_PROGRESS.get(status_enum, (0, "Unknown"))
    except ValueError:
        progress, step = 0, "Unknown"

    errors = []
    if briefing.generation_errors:
        errors = [GenerationError(**e) for e in (briefing.generation_errors or [])]

    pending_action = None
    if briefing.pending_action:
        pending_action = PendingAction(**briefing.pending_action)

    return GenerationStatus(
        briefing_id=briefing.id,
        status=briefing.status,
        progress_percent=progress,
        current_step=step,
        errors=errors,
        pending_action=pending_action,
    )


@router.post("/briefings/{briefing_id}/cancel")
async def cancel_briefing(
    briefing_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Cancel a briefing that is currently generating."""
    result = await session.execute(
        select(Briefing).where(Briefing.id == briefing_id, Briefing.user_id == user.id)
    )
    briefing = result.scalar_one_or_none()

    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    try:
        current_status = BriefingStatus(briefing.status)
    except ValueError:
        current_status = None

    if current_status not in IN_PROGRESS_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel briefing with status: {briefing.status}"
        )

    briefing.status = BriefingStatus.CANCELLED.value
    briefing.pending_action = None
    await session.commit()

    return {"status": "cancelled", "briefing_id": briefing_id}


@router.delete("/briefings/{briefing_id}")
async def delete_briefing(
    briefing_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete a briefing."""
    result = await session.execute(
        select(Briefing).where(Briefing.id == briefing_id, Briefing.user_id == user.id)
    )
    briefing = result.scalar_one_or_none()

    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    audio_path = settings.audio_output_dir / briefing.audio_filename
    if audio_path.exists():
        audio_path.unlink()

    await session.delete(briefing)
    await session.commit()

    return {"status": "deleted", "id": briefing_id}

