"""Main orchestrator for briefing generation using Claude."""

import json
import tempfile
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from src.api.schemas import (
    BriefingStatus,
    LengthMode,
)
from src.briefing.length_rules import LENGTH_RULES
from src.audio.mixer import assemble_briefing_audio
from src.audio.tts import generate_audio_for_script, VOICES
from .generation_errors import (
    GenerationCanceled,
    catch_async_generation_errors,
)
from src.prompts import PromptRenderer
from src.storage.database import Briefing, UserSettings, async_session
from src.tools.music_tools import download_music_audio

from .content import gather_all_content
from .script import generate_briefing_title, generate_script_with_claude

@catch_async_generation_errors(
    fallback_fn=None  # Not recoverable
)
async def get_user_settings(_briefing_id, user_id) -> UserSettings:
    """Get the user's briefing preferences"""
    async with async_session() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        user_settings = result.scalar_one_or_none()
        if not user_settings:
            raise ValueError(f"Couldn't find user settings for user with id {user_id}")
        return user_settings


async def transition_to_phase_or_raise(briefing_id: int, phase: BriefingStatus):
    """
    1. Checks if a briefing has been cancelled.
        If it has, raise an exception with the phase
    2. Updates the briefing status to the next phase
    """
    async with async_session() as session:
        result = await session.execute(
            select(Briefing).where(Briefing.id == briefing_id)
        )
        briefing = result.scalar_one_or_none()
        if briefing is None:
            return
        if briefing.status == BriefingStatus.CANCELLED.value:
            raise GenerationCanceled(phase)
        briefing.status = phase.value
        await session.commit()
    
    print(f"[Briefing {briefing_id}] Transitioned to phase {phase.value}")


async def generate_briefing_task(
    briefing_id: int,
    user_id: Optional[int] = None,
):
    """Background task to generate a complete briefing.

    This is the main entry point called by the API route.

    There are five phases:
        1. Gather the content
        2. Write the script
        3. Do the deep dive
        4. Do TTS and assemble the full audio
        5. Get the title and add to database

    All temp files are managed by a context manager and cleaned up automatically
    regardless of success or failure.

    Args:
        briefing_id: ID of the briefing record to update
        user_id: ID of the user who owns this briefing
    """

    await transition_to_phase_or_raise(briefing_id, BriefingStatus.SETUP)

    # Get user settings for this user
    user_settings = await get_user_settings(briefing_id, user_id)  # Wrapped
    length_mode = LengthMode(user_settings.briefing_length)
    user_timezone = user_settings.timezone
    include_music_enabled = user_settings.include_music
    segment_order = user_settings.segment_order
    writing_style = user_settings.writing_style
    news_exclusions = user_settings.news_exclusions
    voice = VOICES[user_settings.voice_key]

    print(f"[Briefing {briefing_id}] Length mode: {length_mode!r}, Timezone: {user_timezone}")
    prompt_renderer = PromptRenderer()

    # Use a temp directory for all intermediate files - automatically cleaned up
    with tempfile.TemporaryDirectory(prefix=f"briefing_{briefing_id}_") as temp_dir:
        temp_path = Path(temp_dir)
        print(f"[Briefing {briefing_id}] Using temp directory: {temp_path}")

        # Phase 1: Gather content
        await transition_to_phase_or_raise(briefing_id, BriefingStatus.GATHERING_CONTENT)
        content = await gather_all_content(
            briefing_id, user_settings, include_music_enabled, length_mode, user_timezone=user_timezone
        )

        # Phase 2: Generate script with Claude
        await transition_to_phase_or_raise(briefing_id, BriefingStatus.WRITING_SCRIPT)
        deep_dive_count = LENGTH_RULES[length_mode].deep_dive_count if user_settings.deep_dive_enabled else 0

        # Wrapped
        script = await generate_script_with_claude(
            briefing_id, content, length_mode, segment_order, include_music_enabled, writing_style,
            user_timezone=user_timezone,
            prompt_renderer=prompt_renderer,
            news_exclusions=news_exclusions,
            deep_dive_count=deep_dive_count,
        )

        # Phase 3: (Optional) expand any DEEP_DIVE tags with web research
        if deep_dive_count > 0:
            await transition_to_phase_or_raise(briefing_id, BriefingStatus.RESEARCHING_STORIES)
            # TODO call function to get deep dive

        # Phase 4: Generate and assemble audio
        await transition_to_phase_or_raise(briefing_id, BriefingStatus.GENERATING_AUDIO)

        # Download music audio to temp directory if enabled
        music_audio_path: Optional[Path] = None
        if include_music_enabled and content.get("music_piece"):
            music_audio_path = await download_music_audio(
                content["music_piece"],
                output_dir=temp_path,
            )

        # Wrapped
        audio_segments = await generate_audio_for_script(
            briefing_id,
            script,
            voice=voice,
            output_dir=temp_path,
        )
        s3_key, duration_seconds, segments_metadata = await assemble_briefing_audio(
            briefing_id=briefing_id,
            audio_segments=audio_segments,
            include_intro=user_settings.include_intro_music,
            include_transitions=user_settings.include_transitions,
            music_audio_path=music_audio_path,
            temp_dir=temp_path,
        )

    # Temp directory is now cleaned up - continue with finalization

    # Phase 5: Finalize briefing
    await transition_to_phase_or_raise(briefing_id, BriefingStatus.FINALIZING)
   
    # Generate a title
    # Wrapped
    briefing_title = await generate_briefing_title(
        briefing_id, script, user_timezone=user_timezone, prompt_renderer=prompt_renderer
    )

    # Actually update the briefing 
    async with async_session() as session:
        result = await session.execute(
            select(Briefing).where(Briefing.id == briefing_id)
        )
        briefing = result.scalar_one_or_none()

        if briefing:
            # See if any of the previous steps created a generation error
            errors = briefing.generation_errors
            if errors:
                briefing.status = BriefingStatus.COMPLETED_WITH_WARNINGS.value
            else:
                briefing.status = BriefingStatus.COMPLETED.value

            briefing.title = briefing_title
            briefing.duration_seconds = duration_seconds
            briefing.audio_filename = s3_key
            briefing.script = script.model_dump()
            briefing.segments_metadata = segments_metadata
            briefing.pending_action = None
            briefing.rendered_prompts = prompt_renderer.get_all_rendered()
            await session.commit()

    print(f"Briefing {briefing_id} generated successfully!")
