"""Main orchestrator for briefing generation using Claude."""

import json
import traceback
from typing import Optional

from sqlalchemy import select

from src.api.schemas import (
    BriefingStatus,
    DEFAULT_SEGMENT_ORDER,
    DEFAULT_WRITING_STYLE,
    GenerationPhase,
    LengthMode,
)
from src.audio.mixer import assemble_briefing_audio
from src.audio.tts import generate_audio_for_script
from src.prompts import PromptRenderer
from src.storage.database import Briefing, UserSettings, async_session

from .content import gather_all_content
from .script import generate_briefing_title, generate_script_with_claude, process_deep_dive_tags


async def update_briefing_status(briefing_id: int, status: BriefingStatus):
    """Update the status of a briefing in the database."""
    async with async_session() as session:
        result = await session.execute(
            select(Briefing).where(Briefing.id == briefing_id)
        )
        briefing = result.scalar_one_or_none()
        if briefing:
            briefing.status = status.value
            await session.commit()


async def is_briefing_cancelled(briefing_id: int) -> bool:
    """Check if a briefing has been cancelled."""
    async with async_session() as session:
        result = await session.execute(
            select(Briefing.status).where(Briefing.id == briefing_id)
        )
        status = result.scalar_one_or_none()
        return status == BriefingStatus.CANCELLED.value


async def add_generation_error(
    briefing_id: int,
    phase: GenerationPhase,
    component: str,
    message: str,
    recoverable: bool = True,
    fallback_description: Optional[str] = None,
):
    """Add an error to the briefing's error list."""
    async with async_session() as session:
        result = await session.execute(
            select(Briefing).where(Briefing.id == briefing_id)
        )
        briefing = result.scalar_one_or_none()
        if briefing:
            errors = briefing.generation_errors or []
            errors.append({
                "phase": phase.value,
                "component": component,
                "message": message,
                "recoverable": recoverable,
                "fallback_description": fallback_description,
            })
            briefing.generation_errors = errors
            await session.commit()


async def generate_briefing_task(
    briefing_id: int,
    user_id: Optional[int] = None,
    override_length: Optional[LengthMode] = None,
    override_topics: Optional[list[str]] = None,
):
    """Background task to generate a complete briefing.

    This is the main entry point called by the API route.

    Args:
        briefing_id: ID of the briefing record to update
        user_id: ID of the user who owns this briefing
        override_length: Override briefing length (LengthMode.SHORT or LengthMode.LONG)
        override_topics: Override news topics
    """
    try:
        # Get user settings for this user
        async with async_session() as session:
            if user_id:
                result = await session.execute(
                    select(UserSettings).where(UserSettings.user_id == user_id)
                )
            else:
                result = await session.execute(select(UserSettings).limit(1))
            user_settings = result.scalar_one_or_none()

            if not user_settings:
                await add_generation_error(
                    briefing_id, GenerationPhase.SETUP, "settings",
                    "User settings not found", recoverable=False
                )
                await update_briefing_status(briefing_id, BriefingStatus.FAILED)
                return

        # Apply overrides
        if override_length:
            length_mode = override_length
        elif user_settings.briefing_length:
            length_mode = LengthMode(user_settings.briefing_length)
        else:
            length_mode = LengthMode.SHORT
        print(f"[Briefing {briefing_id}] Final length_mode: {length_mode!r}")

        if override_topics:
            user_settings.news_topics = override_topics

        user_timezone = user_settings.timezone or "America/New_York"
        prompt_renderer = PromptRenderer()

        # Phase 1: Gather content
        if await is_briefing_cancelled(briefing_id):
            print(f"[Briefing {briefing_id}] Cancelled before gathering content")
            return

        await update_briefing_status(briefing_id, BriefingStatus.GATHERING_CONTENT)
        include_music_enabled = user_settings.include_music or False

        content = await gather_all_content(
            user_settings, include_music_enabled, length_mode, user_timezone=user_timezone
        )

        # Check for content issues
        if content.get("news") in ("News unavailable.", "No news articles available."):
            await add_generation_error(
                briefing_id, GenerationPhase.GATHERING_CONTENT, "news",
                "News sources returned no content",
                recoverable=True,
                fallback_description="Briefing will skip news segment"
            )

        news_errors = content.get("news_errors", [])
        if news_errors:
            failed_sources = [f"{e.source}/{e.category}" for e in news_errors]
            error_details = "; ".join([f"{e.source}/{e.category}: {e.error_message[:50]}" for e in news_errors[:3]])
            if len(news_errors) > 3:
                error_details += f" ... and {len(news_errors) - 3} more"
            await add_generation_error(
                briefing_id, GenerationPhase.GATHERING_CONTENT, "news_feeds",
                f"Some news feeds failed to load: {error_details}",
                recoverable=True,
                fallback_description=f"Briefing may have fewer news stories. Failed: {', '.join(failed_sources[:5])}"
            )

        weather_content = content.get("weather", "")
        if weather_content in ("Weather unavailable.", "No weather data available."):
            await add_generation_error(
                briefing_id, GenerationPhase.GATHERING_CONTENT, "weather",
                "Weather API returned no content or timed out",
                recoverable=True,
                fallback_description="Briefing will have generic weather fallback"
            )

        if content.get("sports") == "Sports unavailable.":
            await add_generation_error(
                briefing_id, GenerationPhase.GATHERING_CONTENT, "sports",
                "Sports API returned no content",
                recoverable=True,
                fallback_description="Briefing will skip sports segment"
            )

        # Phase 2: Generate script with Claude
        if await is_briefing_cancelled(briefing_id):
            print(f"[Briefing {briefing_id}] Cancelled before writing script")
            return

        await update_briefing_status(briefing_id, BriefingStatus.WRITING_SCRIPT)
        segment_order = user_settings.segment_order or DEFAULT_SEGMENT_ORDER
        writing_style = user_settings.writing_style or DEFAULT_WRITING_STYLE
        news_exclusions = user_settings.news_exclusions or []

        deep_dive_enabled = user_settings.deep_dive_enabled
        if deep_dive_enabled:
            deep_dive_count = 1 if length_mode == LengthMode.SHORT else 2
            print(f"[Briefing {briefing_id}] Deep dive enabled: {deep_dive_count} stories")
        else:
            deep_dive_count = 0

        script = await generate_script_with_claude(
            content, length_mode, segment_order, include_music_enabled, writing_style,
            user_timezone=user_timezone,
            prompt_renderer=prompt_renderer,
            news_exclusions=news_exclusions,
            deep_dive_count=deep_dive_count,
        )

        # Post-process: expand any [DEEP_DIVE] tags with web research
        if deep_dive_count > 0:
            if await is_briefing_cancelled(briefing_id):
                print(f"[Briefing {briefing_id}] Cancelled before deep dive research")
                return

            await update_briefing_status(briefing_id, BriefingStatus.RESEARCHING_STORIES)
            print(f"[Briefing {briefing_id}] Processing deep dive tags...")
            try:
                script = await process_deep_dive_tags(
                    script,
                    writing_style=writing_style,
                    prompt_renderer=prompt_renderer,
                )
            except Exception as e:
                print(f"[Briefing {briefing_id}] Deep dive processing error: {e}")
                await add_generation_error(
                    briefing_id, GenerationPhase.RESEARCHING_STORIES, "deep_dive",
                    f"Deep dive research failed: {str(e)}",
                    recoverable=True,
                    fallback_description="Deep dive stories will use basic coverage"
                )

        # Phase 3: Generate audio
        if await is_briefing_cancelled(briefing_id):
            print(f"[Briefing {briefing_id}] Cancelled before generating audio")
            return

        await update_briefing_status(briefing_id, BriefingStatus.GENERATING_AUDIO)
        tts_provider = user_settings.tts_provider or "elevenlabs"
        voice_id = user_settings.voice_id

        tts_result = await generate_audio_for_script(
            script,
            voice_id=voice_id,
            voice_style=user_settings.voice_style or "energetic",
            voice_speed=user_settings.voice_speed or 1.1,
            tts_provider=tts_provider,
        )

        tts_text_segments = []
        for seg in tts_result.segments:
            tts_text_segments.append({
                "segment_type": seg.segment_type,
                "item_index": seg.item_index,
                "voice_id": seg.voice_id,
                "text": seg.text,
                "duration_seconds": seg.duration_seconds,
            })
        prompt_renderer.add_prompt("tts_segments", json.dumps(tts_text_segments, indent=2))

        if tts_result.has_errors:
            for err in tts_result.errors:
                await add_generation_error(
                    briefing_id, GenerationPhase.GENERATING_AUDIO, f"tts_{err.segment_type}",
                    f"TTS error for {err.segment_type}: {err.error}",
                    recoverable=True,
                    fallback_description=f"Segment '{err.segment_type}' may be incomplete"
                )

        music_audio_path = None
        if include_music_enabled and content.get("music_audio_path"):
            music_audio_path = content["music_audio_path"]
        elif include_music_enabled:
            await add_generation_error(
                briefing_id, GenerationPhase.GENERATING_AUDIO, "music",
                "Music audio not available",
                recoverable=True,
                fallback_description="Briefing will skip music segment"
            )

        # Phase 4: Assemble final audio
        if await is_briefing_cancelled(briefing_id):
            print(f"[Briefing {briefing_id}] Cancelled before assembling audio")
            return

        s3_key, duration_seconds, segments_metadata = await assemble_briefing_audio(
            briefing_id=briefing_id,
            audio_segments=tts_result.segments,
            include_intro=user_settings.include_intro_music,
            include_transitions=user_settings.include_transitions,
            music_audio_path=music_audio_path,
        )

        # Phase 5: Finalize briefing
        if await is_briefing_cancelled(briefing_id):
            print(f"[Briefing {briefing_id}] Cancelled before finalizing")
            return

        await update_briefing_status(briefing_id, BriefingStatus.FINALIZING)

        briefing_title = await generate_briefing_title(
            script, user_timezone=user_timezone, prompt_renderer=prompt_renderer
        )

        async with async_session() as session:
            result = await session.execute(
                select(Briefing).where(Briefing.id == briefing_id)
            )
            briefing = result.scalar_one_or_none()

            if briefing:
                errors = briefing.generation_errors or []
                if errors:
                    briefing.status = BriefingStatus.COMPLETED_WITH_WARNINGS.value
                else:
                    briefing.status = BriefingStatus.COMPLETED.value

                briefing.title = briefing_title
                briefing.duration_seconds = duration_seconds
                briefing.audio_filename = s3_key  # Now stores S3 key instead of filename
                briefing.script = script.model_dump()
                briefing.segments_metadata = segments_metadata
                briefing.pending_action = None
                briefing.rendered_prompts = prompt_renderer.get_all_rendered()
                await session.commit()

        print(f"Briefing {briefing_id} generated successfully!")

    except Exception as e:
        print(f"Error generating briefing {briefing_id}: {e}")
        traceback.print_exc()

        await add_generation_error(
            briefing_id, GenerationPhase.UNKNOWN, "system",
            f"Unexpected error: {str(e)}",
            recoverable=False
        )
        await update_briefing_status(briefing_id, BriefingStatus.FAILED)
