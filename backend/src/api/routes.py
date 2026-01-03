"""API route handlers."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
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

    # Create pending briefing record
    briefing = Briefing(
        title=f"Morning Briefing - {datetime.now().strftime('%B %d, %Y')}",
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
        override_duration=request.override_duration_minutes,
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
    result = await session.execute(
        select(Briefing)
        .where(Briefing.status == "completed")
        .order_by(Briefing.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    briefings = result.scalars().all()

    # Count total
    count_result = await session.execute(
        select(Briefing).where(Briefing.status == "completed")
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
    progress_map = {
        "pending": (0, "Waiting to start..."),
        "gathering_content": (25, "Gathering news, sports, and weather..."),
        "writing_script": (50, "Writing radio script..."),
        "generating_audio": (75, "Generating audio..."),
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
        duration_minutes=user_settings.duration_minutes,
        include_intro_music=user_settings.include_intro_music,
        include_transitions=user_settings.include_transitions,
        news_exclusions=user_settings.news_exclusions or [],
        priority_topics=user_settings.priority_topics or [],
        voice_id=user_settings.voice_id,
        voice_style=user_settings.voice_style,
        voice_speed=user_settings.voice_speed,
        tts_provider=getattr(user_settings, 'tts_provider', None) or "elevenlabs",
        segment_order=user_settings.segment_order or ["news", "sports", "weather", "fun"],
        include_music=user_settings.include_music or False,
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
    for field, value in update_data.items():
        if field == "sports_teams":
            # Convert SportsTeam models to dicts
            value = [t.model_dump() if hasattr(t, "model_dump") else t for t in value]
        elif field == "weather_locations":
            # Convert WeatherLocation models to dicts
            value = [loc.model_dump() if hasattr(loc, "model_dump") else loc for loc in value]
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
        duration_minutes=user_settings.duration_minutes,
        include_intro_music=user_settings.include_intro_music,
        include_transitions=user_settings.include_transitions,
        news_exclusions=user_settings.news_exclusions or [],
        priority_topics=user_settings.priority_topics or [],
        voice_id=user_settings.voice_id,
        voice_style=user_settings.voice_style,
        voice_speed=user_settings.voice_speed,
        tts_provider=getattr(user_settings, 'tts_provider', None) or "elevenlabs",
        segment_order=user_settings.segment_order or ["news", "sports", "weather", "fun"],
        include_music=user_settings.include_music or False,
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
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)

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

    # Get presigned URL for redirect (more efficient for large files)
    url = storage.get_presigned_url(piece.s3_key, expires_hours=1)

    # For now, just redirect to the presigned URL
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=url)


# === Documentation ===


@router.get("/docs", response_class=HTMLResponse)
async def get_documentation():
    """Serve the documentation website."""
    return DOCS_HTML


DOCS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Morning Drive - Documentation</title>
    <style>
        :root {
            --primary: #4f46e5;
            --primary-dark: #3730a3;
            --bg: #f8fafc;
            --card: #ffffff;
            --text: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --success: #22c55e;
            --warning: #f59e0b;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 0 24px; }

        /* Header */
        header {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 60px 0;
            text-align: center;
        }
        header h1 { font-size: 3rem; margin-bottom: 12px; }
        header p { font-size: 1.25rem; opacity: 0.9; }

        /* Navigation */
        nav {
            background: var(--card);
            border-bottom: 1px solid var(--border);
            padding: 16px 0;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        nav ul { display: flex; gap: 32px; list-style: none; justify-content: center; flex-wrap: wrap; }
        nav a { color: var(--text); text-decoration: none; font-weight: 500; }
        nav a:hover { color: var(--primary); }

        /* Main Content */
        main { padding: 48px 0; }
        section { margin-bottom: 48px; }
        h2 {
            color: var(--primary);
            font-size: 1.75rem;
            margin-bottom: 24px;
            padding-bottom: 12px;
            border-bottom: 2px solid var(--border);
        }
        h3 { font-size: 1.25rem; margin: 24px 0 12px; color: var(--text); }
        p { margin-bottom: 16px; color: var(--text-muted); }

        /* Cards */
        .card {
            background: var(--card);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .card h3 { margin-top: 0; color: var(--primary); }

        /* Grid */
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }

        /* Code */
        code {
            background: #f1f5f9;
            padding: 2px 8px;
            border-radius: 4px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.875rem;
        }
        pre {
            background: #1e293b;
            color: #e2e8f0;
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
            margin: 16px 0;
        }
        pre code { background: none; color: inherit; padding: 0; }

        /* Tables */
        table { width: 100%; border-collapse: collapse; margin: 16px 0; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--border); }
        th { background: var(--bg); font-weight: 600; }

        /* Badges */
        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        .badge-get { background: #dbeafe; color: #1d4ed8; }
        .badge-post { background: #dcfce7; color: #15803d; }
        .badge-put { background: #fef3c7; color: #b45309; }
        .badge-delete { background: #fee2e2; color: #dc2626; }

        /* Feature List */
        .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; }
        .feature {
            display: flex;
            align-items: flex-start;
            gap: 12px;
            padding: 16px;
            background: var(--bg);
            border-radius: 8px;
        }
        .feature-icon {
            width: 40px;
            height: 40px;
            background: var(--primary);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 1.25rem;
        }

        /* Footer */
        footer {
            background: var(--text);
            color: white;
            padding: 32px 0;
            text-align: center;
        }
        footer a { color: var(--primary); }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>Morning Drive</h1>
            <p>Your Personalized Morning Briefing App</p>
        </div>
    </header>

    <nav>
        <div class="container">
            <ul>
                <li><a href="#overview">Overview</a></li>
                <li><a href="#architecture">Architecture</a></li>
                <li><a href="#news">News Sources</a></li>
                <li><a href="#audio">Audio Pipeline</a></li>
                <li><a href="#api">API Reference</a></li>
                <li><a href="#settings">Settings</a></li>
            </ul>
        </div>
    </nav>

    <main>
        <div class="container">
            <!-- Overview -->
            <section id="overview">
                <h2>Overview</h2>
                <p>Morning Drive is a personalized morning briefing app that generates professional radio-style audio content. It combines news, sports, weather, and fun segments into a cohesive audio experience perfect for your morning commute.</p>

                <div class="features">
                    <div class="feature">
                        <div class="feature-icon">📰</div>
                        <div>
                            <strong>Curated News</strong>
                            <p>News from your preferred sources and topics</p>
                        </div>
                    </div>
                    <div class="feature">
                        <div class="feature-icon">🏈</div>
                        <div>
                            <strong>Sports Updates</strong>
                            <p>Scores and highlights from your favorite teams</p>
                        </div>
                    </div>
                    <div class="feature">
                        <div class="feature-icon">🌤️</div>
                        <div>
                            <strong>Weather Forecasts</strong>
                            <p>Local weather for your configured locations</p>
                        </div>
                    </div>
                    <div class="feature">
                        <div class="feature-icon">🎙️</div>
                        <div>
                            <strong>Voice Selection</strong>
                            <p>Choose from multiple ElevenLabs voices</p>
                        </div>
                    </div>
                </div>
            </section>

            <!-- Architecture -->
            <section id="architecture">
                <h2>System Architecture</h2>
                <div class="card">
                    <h3>Content Generation Pipeline</h3>
                    <pre><code>┌─────────────────────────────────────────────────────────────┐
│                    Content Gathering                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │  News    │ │  Sports  │ │ Weather  │ │  Fun Segment │   │
│  │  Agent   │ │  Agent   │ │  Agent   │ │    Agent     │   │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘   │
│       └────────────┴────────────┴──────────────┘           │
│                           │                                 │
│                           ▼                                 │
│              ┌────────────────────────┐                    │
│              │  Claude Script Writer  │                    │
│              │  (Radio-style script)  │                    │
│              └───────────┬────────────┘                    │
│                          │                                  │
│                          ▼                                  │
│              ┌────────────────────────┐                    │
│              │   ElevenLabs TTS       │                    │
│              │   (Voice synthesis)    │                    │
│              └───────────┬────────────┘                    │
│                          │                                  │
│                          ▼                                  │
│              ┌────────────────────────┐                    │
│              │   Audio Mixer          │                    │
│              │   (Jingles + Stings)   │                    │
│              └───────────┬────────────┘                    │
│                          │                                  │
│                          ▼                                  │
│                   Final MP3 Audio                          │
└─────────────────────────────────────────────────────────────┘</code></pre>
                </div>
            </section>

            <!-- News Sources -->
            <section id="news">
                <h2>News Sources</h2>
                <div class="grid">
                    <div class="card">
                        <h3>RSS Feeds (Primary)</h3>
                        <p>Free, reliable news feeds from major outlets:</p>
                        <ul>
                            <li><strong>BBC News</strong> - World, Tech, Business</li>
                            <li><strong>Reuters</strong> - Breaking news</li>
                            <li><strong>NPR</strong> - US news and culture</li>
                            <li><strong>Associated Press</strong> - Wire service</li>
                            <li><strong>TechCrunch</strong> - Tech industry</li>
                            <li><strong>Hacker News</strong> - Tech community</li>
                            <li><strong>Ars Technica</strong> - Tech deep-dives</li>
                        </ul>
                    </div>
                    <div class="card">
                        <h3>Content Filtering</h3>
                        <p>Your briefing content is personalized using:</p>
                        <ul>
                            <li><strong>Priority Topics</strong> - Topics to emphasize (e.g., "AI news", "tech startups")</li>
                            <li><strong>Exclusions</strong> - Topics to skip (e.g., "celebrity gossip")</li>
                            <li><strong>Categories</strong> - Tech, Business, World, Science, etc.</li>
                        </ul>
                        <p>Claude AI filters and ranks stories based on your preferences.</p>
                    </div>
                </div>
            </section>

            <!-- Audio Pipeline -->
            <section id="audio">
                <h2>Audio Pipeline</h2>
                <div class="card">
                    <h3>Production Elements</h3>
                    <table>
                        <tr><th>Element</th><th>Description</th><th>Timing</th></tr>
                        <tr><td>Intro Jingle</td><td>Upbeat opening melody</td><td>~2 seconds</td></tr>
                        <tr><td>News Sting</td><td>News section intro</td><td>~0.5 seconds</td></tr>
                        <tr><td>Sports Sting</td><td>Sports section intro</td><td>~0.8 seconds</td></tr>
                        <tr><td>Weather Sting</td><td>Weather section intro</td><td>~0.7 seconds</td></tr>
                        <tr><td>Transition Whoosh</td><td>Between major sections</td><td>~0.4 seconds</td></tr>
                        <tr><td>Outro Jingle</td><td>Pleasant closing</td><td>~2 seconds</td></tr>
                    </table>
                </div>
                <div class="card">
                    <h3>Voice Styles</h3>
                    <table>
                        <tr><th>Style</th><th>Description</th><th>Best For</th></tr>
                        <tr><td>Energetic</td><td>Upbeat morning show vibe, more expressive</td><td>Morning commute</td></tr>
                        <tr><td>Professional</td><td>News anchor style, measured delivery</td><td>Business briefings</td></tr>
                        <tr><td>Calm</td><td>Relaxed, soothing delivery</td><td>Quiet mornings</td></tr>
                    </table>
                </div>
            </section>

            <!-- API Reference -->
            <section id="api">
                <h2>API Reference</h2>

                <div class="card">
                    <h3>Briefings</h3>
                    <table>
                        <tr><th>Method</th><th>Endpoint</th><th>Description</th></tr>
                        <tr>
                            <td><span class="badge badge-post">POST</span></td>
                            <td><code>/api/briefings/generate</code></td>
                            <td>Trigger new briefing generation</td>
                        </tr>
                        <tr>
                            <td><span class="badge badge-get">GET</span></td>
                            <td><code>/api/briefings</code></td>
                            <td>List all briefings</td>
                        </tr>
                        <tr>
                            <td><span class="badge badge-get">GET</span></td>
                            <td><code>/api/briefings/{id}</code></td>
                            <td>Get briefing details</td>
                        </tr>
                        <tr>
                            <td><span class="badge badge-get">GET</span></td>
                            <td><code>/api/briefings/{id}/status</code></td>
                            <td>Check generation progress</td>
                        </tr>
                        <tr>
                            <td><span class="badge badge-delete">DELETE</span></td>
                            <td><code>/api/briefings/{id}</code></td>
                            <td>Delete a briefing</td>
                        </tr>
                    </table>
                </div>

                <div class="card">
                    <h3>Settings & Schedule</h3>
                    <table>
                        <tr><th>Method</th><th>Endpoint</th><th>Description</th></tr>
                        <tr>
                            <td><span class="badge badge-get">GET</span></td>
                            <td><code>/api/settings</code></td>
                            <td>Get current settings</td>
                        </tr>
                        <tr>
                            <td><span class="badge badge-put">PUT</span></td>
                            <td><code>/api/settings</code></td>
                            <td>Update settings</td>
                        </tr>
                        <tr>
                            <td><span class="badge badge-get">GET</span></td>
                            <td><code>/api/schedule</code></td>
                            <td>Get generation schedule</td>
                        </tr>
                        <tr>
                            <td><span class="badge badge-put">PUT</span></td>
                            <td><code>/api/schedule</code></td>
                            <td>Update schedule</td>
                        </tr>
                    </table>
                </div>
            </section>

            <!-- Settings -->
            <section id="settings">
                <h2>Settings Reference</h2>
                <div class="grid">
                    <div class="card">
                        <h3>Content Settings</h3>
                        <ul>
                            <li><strong>news_topics</strong> - Categories: top, world, technology, business, science, health, entertainment</li>
                            <li><strong>news_sources</strong> - Sources: bbc, reuters, npr, nyt, ap, techcrunch, hackernews, arstechnica</li>
                            <li><strong>priority_topics</strong> - Custom topics to emphasize</li>
                            <li><strong>news_exclusions</strong> - Custom topics to skip</li>
                            <li><strong>sports_leagues</strong> - nfl, mlb, nhl, nba, mls, premier_league, atp, wta, pga</li>
                            <li><strong>fun_segments</strong> - this_day_in_history, quote_of_the_day, market_minute, word_of_the_day, dad_joke, sports_history</li>
                        </ul>
                    </div>
                    <div class="card">
                        <h3>Audio Settings</h3>
                        <ul>
                            <li><strong>duration_minutes</strong> - Briefing length (5-30 min)</li>
                            <li><strong>include_intro_music</strong> - Enable jingles</li>
                            <li><strong>include_transitions</strong> - Enable section stings</li>
                            <li><strong>voice_id</strong> - ElevenLabs voice ID</li>
                            <li><strong>voice_style</strong> - energetic, professional, calm</li>
                            <li><strong>voice_speed</strong> - 0.9x to 1.2x</li>
                        </ul>
                    </div>
                    <div class="card">
                        <h3>Schedule Settings</h3>
                        <ul>
                            <li><strong>enabled</strong> - Enable auto-generation</li>
                            <li><strong>days_of_week</strong> - 0=Monday to 6=Sunday</li>
                            <li><strong>time_hour</strong> - Hour (0-23)</li>
                            <li><strong>time_minute</strong> - Minute (0-59)</li>
                            <li><strong>timezone</strong> - e.g., America/New_York</li>
                        </ul>
                    </div>
                </div>
            </section>
        </div>
    </main>

    <footer>
        <div class="container">
            <p>Morning Drive &copy; 2025 | Built with FastAPI + Claude + ElevenLabs</p>
        </div>
    </footer>
</body>
</html>
"""
