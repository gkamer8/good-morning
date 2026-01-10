"""API route handlers."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    BriefingCreate,
    BriefingListResponse,
    BriefingResponse,
    BriefingSegment,
    ErrorResolution,
    GenerationError,
    GenerationStatus,
    MusicPieceListResponse,
    MusicPieceResponse,
    MusicPieceUpdate,
    PendingAction,
    ScheduleResponse,
    ScheduleUpdate,
    SettingsResponse,
    SettingsUpdate,
)
from src.config import get_settings
from src.storage.database import Briefing, MusicPiece, Schedule, UserSettings, get_session

# Stock ElevenLabs voice IDs (Rachel, Adam, Arnold)
STOCK_VOICE_IDS = {
    "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "pNInz6obpgDQGcFmaJgB",  # Adam
    "VR6AewLTigWG4xSOukaG",  # Arnold
}
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel


def get_valid_voice_ids() -> set:
    """Get all valid voice IDs including stock and custom voices."""
    settings = get_settings()
    custom_voice_ids = set(settings.elevenlabs_custom_voice_ids or [])
    return STOCK_VOICE_IDS | custom_voice_ids

router = APIRouter()
settings = get_settings()


# === Briefings ===


@router.post("/briefings/generate", response_model=GenerationStatus)
async def generate_briefing(
    request: BriefingCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Trigger generation of a new morning briefing."""
    from src.agents.orchestrator import generate_briefing_task
    from src.utils.timezone import get_user_now

    # Get user timezone for the title
    result = await session.execute(select(UserSettings).limit(1))
    user_settings = result.scalar_one_or_none()
    user_tz = getattr(user_settings, 'timezone', None) or "America/New_York"
    user_now = get_user_now(user_tz)

    # Create pending briefing record
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

    # Start generation in background
    background_tasks.add_task(
        generate_briefing_task,
        briefing_id=briefing.id,
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
    session: AsyncSession = Depends(get_session),
):
    """List all available briefings."""
    # Include both completed and completed_with_warnings
    completed_statuses = ["completed", "completed_with_warnings"]
    result = await session.execute(
        select(Briefing)
        .where(Briefing.status.in_(completed_statuses))
        .order_by(Briefing.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    briefings = result.scalars().all()

    # Count total
    count_result = await session.execute(
        select(Briefing).where(Briefing.status.in_(completed_statuses))
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
    session: AsyncSession = Depends(get_session),
):
    """Get a specific briefing by ID."""
    result = await session.execute(select(Briefing).where(Briefing.id == briefing_id))
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
    session: AsyncSession = Depends(get_session),
):
    """Get the generation status of a briefing."""
    result = await session.execute(select(Briefing).where(Briefing.id == briefing_id))
    briefing = result.scalar_one_or_none()

    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    # Determine progress based on status
    # Percentages represent progress at START of each phase (what user sees during that phase):
    # - gathering_content: ~3s → show 2% (just started)
    # - writing_script: ~15s → show 8% (content done)
    # - researching_stories: ~20s → show 25% (script done)
    # - generating_audio: ~45s → show 50% (longest phase, halfway through total)
    # - finalizing: ~2s → show 95% (audio done, almost complete)
    progress_map = {
        "pending": (0, "Waiting to start..."),
        "gathering_content": (2, "Gathering news, sports, and weather..."),
        "writing_script": (8, "Writing radio script..."),
        "researching_stories": (25, "Researching stories in depth..."),
        "generating_audio": (50, "Generating audio..."),
        "finalizing": (95, "Finalizing your briefing..."),
        "awaiting_confirmation": (None, "Waiting for your decision..."),  # Progress stays where it was
        "completed": (100, "Complete!"),
        "completed_with_warnings": (100, "Complete (with warnings)"),
        "failed": (0, "Generation failed"),
        "cancelled": (0, "Cancelled"),
    }
    progress, step = progress_map.get(briefing.status, (0, "Unknown"))

    # Keep progress at previous value for awaiting_confirmation
    if progress is None:
        # Estimate based on where we paused
        progress = 50  # Default to middle

    # Parse errors from database
    errors = []
    if briefing.generation_errors:
        errors = [GenerationError(**e) for e in (briefing.generation_errors or [])]

    # Parse pending action
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


@router.post("/briefings/{briefing_id}/resolve")
async def resolve_briefing_error(
    briefing_id: int,
    resolution: ErrorResolution,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Resolve a pending error during generation.

    Actions:
    - "continue": Use fallback and continue generation
    - "cancel": Cancel the generation entirely
    - "retry": Retry the failed operation
    """
    result = await session.execute(select(Briefing).where(Briefing.id == briefing_id))
    briefing = result.scalar_one_or_none()

    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    if briefing.status != "awaiting_confirmation":
        raise HTTPException(
            status_code=400,
            detail=f"Briefing is not awaiting confirmation (status: {briefing.status})"
        )

    if not briefing.pending_action:
        raise HTTPException(status_code=400, detail="No pending action to resolve")

    # Verify action_id matches
    if briefing.pending_action.get("action_id") != resolution.action_id:
        raise HTTPException(status_code=400, detail="Action ID mismatch")

    if resolution.decision == "cancel":
        briefing.status = "cancelled"
        briefing.pending_action = None
        await session.commit()
        return {"status": "cancelled", "briefing_id": briefing_id}

    elif resolution.decision in ("continue", "retry"):
        # Store the decision and clear pending action
        # The background task will check for this and resume
        briefing.pending_action = {
            **briefing.pending_action,
            "resolved": True,
            "decision": resolution.decision,
        }
        await session.commit()

        return {
            "status": "resuming",
            "briefing_id": briefing_id,
            "decision": resolution.decision,
        }

    else:
        raise HTTPException(status_code=400, detail=f"Invalid decision: {resolution.decision}")


@router.post("/briefings/{briefing_id}/cancel")
async def cancel_briefing(
    briefing_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Cancel a briefing that is currently generating.

    This marks the briefing as cancelled in the database. The background task
    will check this status periodically and stop processing if cancelled.
    """
    result = await session.execute(select(Briefing).where(Briefing.id == briefing_id))
    briefing = result.scalar_one_or_none()

    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    # Only allow cancelling briefings that are in progress
    in_progress_statuses = {
        "pending", "gathering_content", "writing_script", "researching_stories",
        "generating_audio", "assembling_audio", "finalizing", "awaiting_confirmation"
    }

    if briefing.status not in in_progress_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel briefing with status: {briefing.status}"
        )

    briefing.status = "cancelled"
    briefing.pending_action = None  # Clear any pending action
    await session.commit()

    return {"status": "cancelled", "briefing_id": briefing_id}


@router.delete("/briefings/{briefing_id}")
async def delete_briefing(
    briefing_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a briefing."""
    result = await session.execute(select(Briefing).where(Briefing.id == briefing_id))
    briefing = result.scalar_one_or_none()

    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")

    # Delete audio file
    audio_path = settings.audio_output_dir / briefing.audio_filename
    if audio_path.exists():
        audio_path.unlink()

    await session.delete(briefing)
    await session.commit()

    return {"status": "deleted", "id": briefing_id}


# === Settings ===


@router.get("/settings", response_model=SettingsResponse)
async def get_settings_endpoint(
    session: AsyncSession = Depends(get_session),
):
    """Get current user settings."""
    result = await session.execute(select(UserSettings).limit(1))
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        raise HTTPException(status_code=404, detail="Settings not found")

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
        voice_id=user_settings.voice_id,
        voice_style=user_settings.voice_style,
        voice_speed=user_settings.voice_speed,
        tts_provider=getattr(user_settings, 'tts_provider', None) or "elevenlabs",
        segment_order=user_settings.segment_order or ["news", "sports", "weather", "fun"],
        include_music=user_settings.include_music or False,
        writing_style=getattr(user_settings, 'writing_style', None) or "good_morning_america",
        timezone=getattr(user_settings, 'timezone', None) or "America/New_York",
        deep_dive_enabled=getattr(user_settings, 'deep_dive_enabled', False),
        updated_at=user_settings.updated_at,
    )


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    update: SettingsUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update user settings."""
    result = await session.execute(select(UserSettings).limit(1))
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    # Update fields
    update_data = update.model_dump(exclude_unset=True)

    # Log briefing_length changes for debugging
    if "briefing_length" in update_data:
        print(f"[Settings] Updating briefing_length: {user_settings.briefing_length!r} -> {update_data['briefing_length']!r}")

    for field, value in update_data.items():
        if field == "sports_teams":
            # Convert SportsTeam models to dicts
            value = [t.model_dump() if hasattr(t, "model_dump") else t for t in value]
        elif field == "weather_locations":
            # Convert WeatherLocation models to dicts
            value = [loc.model_dump() if hasattr(loc, "model_dump") else loc for loc in value]
        elif field == "voice_id":
            # Validate voice_id - use default if invalid
            # Include both stock voices and custom voices from settings
            if value not in get_valid_voice_ids():
                value = DEFAULT_VOICE_ID
        setattr(user_settings, field, value)

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
        voice_id=user_settings.voice_id,
        voice_style=user_settings.voice_style,
        voice_speed=user_settings.voice_speed,
        tts_provider=getattr(user_settings, 'tts_provider', None) or "elevenlabs",
        segment_order=user_settings.segment_order or ["news", "sports", "weather", "fun"],
        include_music=user_settings.include_music or False,
        writing_style=getattr(user_settings, 'writing_style', None) or "good_morning_america",
        timezone=getattr(user_settings, 'timezone', None) or "America/New_York",
        deep_dive_enabled=getattr(user_settings, 'deep_dive_enabled', False),
        updated_at=user_settings.updated_at,
    )


# === Schedule ===


@router.get("/schedule", response_model=ScheduleResponse)
async def get_schedule(
    session: AsyncSession = Depends(get_session),
):
    """Get the current generation schedule."""
    result = await session.execute(select(Schedule).limit(1))
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return ScheduleResponse(
        id=schedule.id,
        enabled=schedule.enabled,
        days_of_week=schedule.days_of_week,
        time_hour=schedule.time_hour,
        time_minute=schedule.time_minute,
        timezone=schedule.timezone,
        next_run=None,  # TODO: Calculate next run time
    )


@router.put("/schedule", response_model=ScheduleResponse)
async def update_schedule(
    update: ScheduleUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update the generation schedule."""
    result = await session.execute(select(Schedule).limit(1))
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # Update fields
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(schedule, field, value)

    # Sync timezone to UserSettings if it was updated
    if "timezone" in update_data:
        settings_result = await session.execute(select(UserSettings).limit(1))
        user_settings = settings_result.scalar_one_or_none()
        if user_settings:
            user_settings.timezone = schedule.timezone

    await session.commit()
    await session.refresh(schedule)

    # Update the running scheduler with new settings
    from src.main import get_scheduler
    from src.scheduler import create_scheduled_briefing
    from apscheduler.triggers.cron import CronTrigger
    from zoneinfo import ZoneInfo

    scheduler = get_scheduler()
    if scheduler and scheduler.running:
        # Remove existing job if present
        if scheduler.get_job("morning_briefing"):
            scheduler.remove_job("morning_briefing")

        # Add new job if schedule is enabled
        if schedule.enabled:
            days_str = ",".join(str(d) for d in schedule.days_of_week)
            trigger = CronTrigger(
                hour=schedule.time_hour,
                minute=schedule.time_minute,
                day_of_week=days_str,
                timezone=ZoneInfo(schedule.timezone),
            )
            scheduler.add_job(
                create_scheduled_briefing,
                trigger,
                id="morning_briefing",
                name="Morning Briefing Generation",
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


# === Voices ===


@router.get("/voices")
async def list_voices():
    """List all available ElevenLabs voices including custom voices."""
    from src.audio.tts import list_available_voices

    voices = await list_available_voices()
    return {"voices": voices, "total": len(voices)}


PREVIEW_TEXT = "Good morning! This is your Morning Drive briefing for today. Let's get you caught up on what's happening."


@router.get("/voices/{voice_id}/preview")
async def get_voice_preview(voice_id: str):
    """Get or generate a voice preview audio sample."""
    from pathlib import Path
    from elevenlabs import ElevenLabs

    # Preview directory
    preview_dir = settings.audio_output_dir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)

    # Check if preview already exists and is valid (non-empty)
    preview_path = preview_dir / f"{voice_id}.mp3"

    needs_generation = False
    if not preview_path.exists():
        needs_generation = True
    elif preview_path.stat().st_size == 0:
        # Empty file from a previous failed generation - delete it
        preview_path.unlink()
        needs_generation = True

    if needs_generation:
        # Generate preview
        if not settings.elevenlabs_api_key:
            raise HTTPException(status_code=500, detail="ElevenLabs API key not configured")

        try:
            client = ElevenLabs(api_key=settings.elevenlabs_api_key)

            audio_generator = client.text_to_speech.convert(
                voice_id=voice_id,
                text=PREVIEW_TEXT,
                model_id=settings.elevenlabs_model_id,
                output_format="mp3_44100_128",
                voice_settings={
                    "stability": 0.35,
                    "similarity_boost": 0.75,
                    "style": 0.65,
                    "use_speaker_boost": True,
                },
            )

            # Write to a temp file first, then rename to avoid partial files
            temp_path = preview_dir / f"{voice_id}.tmp.mp3"
            bytes_written = 0
            with open(temp_path, "wb") as f:
                for chunk in audio_generator:
                    f.write(chunk)
                    bytes_written += len(chunk)

            # Verify we got actual audio data
            if bytes_written == 0:
                temp_path.unlink()
                raise HTTPException(
                    status_code=500,
                    detail=f"ElevenLabs returned empty audio for voice {voice_id}"
                )

            # Move temp file to final location
            temp_path.rename(preview_path)

        except HTTPException:
            raise
        except Exception as e:
            # Clean up any partial file
            if preview_path.exists() and preview_path.stat().st_size == 0:
                preview_path.unlink()
            raise HTTPException(status_code=500, detail=f"Failed to generate preview: {str(e)}")

    return FileResponse(
        preview_path,
        media_type="audio/mpeg",
        filename=f"voice_preview_{voice_id}.mp3",
    )


# === Music ===


@router.get("/music", response_model=MusicPieceListResponse)
async def list_music_pieces(
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
):
    """List all available music pieces."""
    query = select(MusicPiece)
    if active_only:
        query = query.where(MusicPiece.is_active == True)
    query = query.order_by(MusicPiece.composer, MusicPiece.title)

    result = await session.execute(query)
    pieces = result.scalars().all()

    return MusicPieceListResponse(
        pieces=[
            MusicPieceResponse(
                id=p.id,
                created_at=p.created_at,
                title=p.title,
                composer=p.composer,
                description=p.description,
                s3_key=p.s3_key,
                duration_seconds=p.duration_seconds,
                file_size_bytes=p.file_size_bytes,
                day_of_year_start=p.day_of_year_start,
                day_of_year_end=p.day_of_year_end,
                is_active=p.is_active,
            )
            for p in pieces
        ],
        total=len(pieces),
    )


@router.get("/music/{piece_id}", response_model=MusicPieceResponse)
async def get_music_piece(
    piece_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get a specific music piece by ID."""
    result = await session.execute(select(MusicPiece).where(MusicPiece.id == piece_id))
    piece = result.scalar_one_or_none()

    if not piece:
        raise HTTPException(status_code=404, detail="Music piece not found")

    return MusicPieceResponse(
        id=piece.id,
        created_at=piece.created_at,
        title=piece.title,
        composer=piece.composer,
        description=piece.description,
        s3_key=piece.s3_key,
        duration_seconds=piece.duration_seconds,
        file_size_bytes=piece.file_size_bytes,
        day_of_year_start=piece.day_of_year_start,
        day_of_year_end=piece.day_of_year_end,
        is_active=piece.is_active,
    )


@router.post("/music", response_model=MusicPieceResponse)
async def upload_music_piece(
    title: str,
    composer: str,
    duration_seconds: float,
    file: UploadFile,
    description: Optional[str] = None,
    day_of_year_start: int = 1,
    day_of_year_end: int = 366,
    session: AsyncSession = Depends(get_session),
):
    """Upload a new music piece with audio file to MinIO."""
    from src.storage.minio_storage import get_minio_storage

    # Validate file type
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    # Generate S3 key
    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title).strip()
    safe_composer = "".join(c if c.isalnum() or c in " -_" else "" for c in composer).strip()
    s3_key = f"music/{safe_composer}/{safe_title}.mp3".replace(" ", "_").lower()

    # Read file content
    content = await file.read()
    if len(content) < 10000:
        raise HTTPException(status_code=400, detail="File too small to be valid audio")

    # Upload to MinIO
    storage = get_minio_storage()
    await storage.ensure_bucket_exists()
    result = await storage.upload_bytes(content, s3_key, content_type=file.content_type or "audio/mpeg")

    # Create database record
    piece = MusicPiece(
        title=title,
        composer=composer,
        description=description,
        s3_key=s3_key,
        duration_seconds=duration_seconds,
        file_size_bytes=result["size_bytes"],
        day_of_year_start=day_of_year_start,
        day_of_year_end=day_of_year_end,
        is_active=True,
    )
    session.add(piece)
    await session.commit()
    await session.refresh(piece)

    return MusicPieceResponse(
        id=piece.id,
        created_at=piece.created_at,
        title=piece.title,
        composer=piece.composer,
        description=piece.description,
        s3_key=piece.s3_key,
        duration_seconds=piece.duration_seconds,
        file_size_bytes=piece.file_size_bytes,
        day_of_year_start=piece.day_of_year_start,
        day_of_year_end=piece.day_of_year_end,
        is_active=piece.is_active,
    )


@router.put("/music/{piece_id}", response_model=MusicPieceResponse)
async def update_music_piece(
    piece_id: int,
    update: MusicPieceUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update music piece metadata."""
    result = await session.execute(select(MusicPiece).where(MusicPiece.id == piece_id))
    piece = result.scalar_one_or_none()

    if not piece:
        raise HTTPException(status_code=404, detail="Music piece not found")

    # Update fields
    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(piece, field, value)

    await session.commit()
    await session.refresh(piece)

    return MusicPieceResponse(
        id=piece.id,
        created_at=piece.created_at,
        title=piece.title,
        composer=piece.composer,
        description=piece.description,
        s3_key=piece.s3_key,
        duration_seconds=piece.duration_seconds,
        file_size_bytes=piece.file_size_bytes,
        day_of_year_start=piece.day_of_year_start,
        day_of_year_end=piece.day_of_year_end,
        is_active=piece.is_active,
    )


@router.delete("/music/{piece_id}")
async def delete_music_piece(
    piece_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a music piece (from both database and MinIO)."""
    from src.storage.minio_storage import get_minio_storage

    result = await session.execute(select(MusicPiece).where(MusicPiece.id == piece_id))
    piece = result.scalar_one_or_none()

    if not piece:
        raise HTTPException(status_code=404, detail="Music piece not found")

    # Delete from MinIO
    storage = get_minio_storage()
    await storage.delete_file(piece.s3_key)

    # Delete from database
    await session.delete(piece)
    await session.commit()

    return {"status": "deleted", "id": piece_id}


@router.get("/music/{piece_id}/stream")
async def stream_music_piece(
    piece_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Stream a music piece audio file."""
    from fastapi.responses import StreamingResponse
    from src.storage.minio_storage import get_minio_storage

    result = await session.execute(select(MusicPiece).where(MusicPiece.id == piece_id))
    piece = result.scalar_one_or_none()

    if not piece:
        raise HTTPException(status_code=404, detail="Music piece not found")

    storage = get_minio_storage()

    # Check if file exists
    if not await storage.file_exists(piece.s3_key):
        raise HTTPException(status_code=404, detail="Audio file not found in storage")

    # Stream through the backend (MinIO internal hostname not accessible from browser)
    def iter_file():
        response = storage.get_file_stream(piece.s3_key)
        try:
            for chunk in response.stream(32 * 1024):  # 32KB chunks
                yield chunk
        finally:
            response.close()
            response.release_conn()

    return StreamingResponse(
        iter_file(),
        media_type="audio/mpeg",
        headers={
            "Content-Length": str(piece.file_size_bytes),
            "Accept-Ranges": "bytes",
        }
    )
