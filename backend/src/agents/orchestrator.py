"""Main orchestrator for briefing generation using Claude."""

import asyncio
import json
from datetime import datetime
from typing import Optional

from anthropic import AsyncAnthropic
from sqlalchemy import select

from src.api.schemas import BriefingScript, ScriptSegment, ScriptSegmentItem
from src.audio.mixer import assemble_briefing_audio
from src.audio.tts import generate_audio_for_script
from src.config import get_settings
from src.storage.database import Briefing, UserSettings, async_session
from src.tools.finance_tools import format_market_for_agent, get_market_summary
from src.tools.fun_tools import format_fun_content_for_agent, get_fun_content
from src.tools.news_tools import format_news_for_agent, get_top_news
from src.tools.sports_tools import (
    format_sports_for_agent,
    get_scores_for_leagues,
    get_sports_news,
    get_team_updates,
)
from src.tools.weather_tools import format_weather_for_agent, get_weather_for_locations
from src.tools.music_tools import (
    format_music_for_agent,
    get_music_with_audio,
)


SCRIPT_WRITER_SYSTEM_PROMPT_TEMPLATE = """You are a professional radio scriptwriter for "Morning Drive," a personalized morning briefing show. Your job is to transform raw news, sports, weather, and fun content into an engaging, conversational radio script.

STYLE GUIDELINES:
- Write in a warm, professional radio host voice
- Use natural transitions between segments
- Keep language accessible but intelligent
- Include brief pauses where appropriate (indicated by "...")
- Vary sentence length for natural rhythm
- When reading quotes, indicate the voice profile needed based on the speaker's likely demographics

STRUCTURE:
- Open with a friendly greeting and the date
- Flow naturally between segments in this order: {segment_flow}
- Each segment should feel connected, not abrupt
- End with an upbeat sign-off
- IMPORTANT: You must follow the exact segment order specified above
{classical_music_instruction}

QUOTE HANDLING:
When including quotes from real people, format them like this:
[QUOTE: voice_profile="demographic_description" attribution="Person Name"]
Quote text here
[/QUOTE]

For voice_profile, describe demographics that would help match a voice:
- male_american_30s, female_british_40s, male_older_60s, etc.
- Include nationality/accent if relevant (e.g., "male_icelandic_50s")

OUTPUT FORMAT:
Return a JSON object with this structure:
{{
  "segments": [
    {{
      "type": "intro|news|sports|weather|fun|outro",
      "items": [
        {{
          "voice": "host",
          "text": "Script text here"
        }},
        {{
          "voice": "quote",
          "voice_profile": "demographic description",
          "text": "Quote text",
          "attribution": "Speaker name"
        }}
      ]
    }}
  ]
}}

Only return valid JSON, no other text or markdown."""


async def gather_all_content(settings: UserSettings, include_music: bool = False) -> dict:
    """Gather content from all sources in parallel."""

    # Prepare tasks
    async def fetch_news():
        articles = await get_top_news(
            sources=settings.news_sources or ["bbc", "npr", "nyt"],
            topics=settings.news_topics or ["top", "technology", "business"],
            limit=10,
        )
        return format_news_for_agent(articles)

    async def fetch_sports():
        leagues = settings.sports_leagues or ["nfl", "mlb", "nhl"]
        teams = settings.sports_teams or []

        scores = await get_scores_for_leagues(leagues)
        news = await get_sports_news(leagues, limit_per_league=2)
        team_games = await get_team_updates(teams) if teams else []

        return format_sports_for_agent(scores, news, team_games)

    async def fetch_weather():
        locations = settings.weather_locations or [
            {"name": "New York", "lat": 40.7128, "lon": -74.0060}
        ]
        forecasts = await get_weather_for_locations(locations)
        return format_weather_for_agent(forecasts)

    async def fetch_fun():
        segments = settings.fun_segments or [
            "this_day_in_history",
            "quote_of_the_day",
        ]
        content = await get_fun_content(segments)
        return format_fun_content_for_agent(content)

    async def fetch_market():
        if "market_minute" in (settings.fun_segments or []):
            summary = await get_market_summary()
            return format_market_for_agent(summary)
        return ""

    async def fetch_music():
        if include_music:
            today = datetime.now().strftime("%Y-%m-%d")

            # Get music piece and audio from database/MinIO
            audio_path, piece = await get_music_with_audio(today)

            if audio_path and piece:
                return {
                    "text": format_music_for_agent(piece),
                    "piece": piece,
                    "audio_path": audio_path,
                }
            elif piece:
                # Piece found but audio unavailable
                print(f"WARNING: Music audio unavailable for {piece.title}, skipping music playback")
                return {
                    "text": format_music_for_agent(piece),
                    "piece": piece,
                    "audio_path": None,
                }
            else:
                # No pieces available at all
                print("WARNING: No music pieces available in database")
                return {"text": "", "piece": None, "audio_path": None}
        return {"text": "", "piece": None, "audio_path": None}

    # Run all fetches in parallel
    results = await asyncio.gather(
        fetch_news(),
        fetch_sports(),
        fetch_weather(),
        fetch_fun(),
        fetch_market(),
        fetch_music(),
        return_exceptions=True,
    )

    # Handle any errors gracefully
    # Music result is a dict with "text", "piece", and "audio_path" keys
    music_result = results[5] if not isinstance(results[5], Exception) else {"text": "", "piece": None, "audio_path": None}

    content = {
        "news": results[0] if not isinstance(results[0], Exception) else "News unavailable.",
        "sports": results[1] if not isinstance(results[1], Exception) else "Sports unavailable.",
        "weather": results[2] if not isinstance(results[2], Exception) else "Weather unavailable.",
        "fun": results[3] if not isinstance(results[3], Exception) else "",
        "market": results[4] if not isinstance(results[4], Exception) else "",
        "music": music_result.get("text", "") if isinstance(music_result, dict) else "",
        "music_piece": music_result.get("piece") if isinstance(music_result, dict) else None,
        "music_audio_path": music_result.get("audio_path") if isinstance(music_result, dict) else None,
    }

    return content


SEGMENT_DISPLAY_NAMES = {
    "news": "News",
    "sports": "Sports",
    "weather": "Weather",
    "fun": "Fun segments",
}


async def generate_script_with_claude(
    content: dict,
    target_duration_minutes: int,
    segment_order: list[str] = None,
    include_music: bool = False,
) -> BriefingScript:
    """Use Claude to generate the radio script."""
    settings = get_settings()

    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Use default order if not provided
    if not segment_order:
        segment_order = ["news", "sports", "weather", "fun"]

    # Build the segment flow string for the prompt
    segment_names = [SEGMENT_DISPLAY_NAMES.get(s, s.title()) for s in segment_order]
    segment_flow = " → ".join(segment_names) + " → Sign off"

    # Add music instruction if enabled
    if include_music:
        music_instruction = """
- MUSIC: After the sign-off, include a "music" segment that introduces the music piece.
  The introduction should be warm and engaging, helping listeners appreciate what they're about to hear."""
    else:
        music_instruction = ""

    # Build the system prompt with the dynamic segment order
    system_prompt = SCRIPT_WRITER_SYSTEM_PROMPT_TEMPLATE.format(
        segment_flow=segment_flow,
        classical_music_instruction=music_instruction,
    )

    # Build content sections in the user-specified order
    content_sections = []
    for segment_type in segment_order:
        if segment_type == "news" and content.get("news"):
            content_sections.append(content["news"])
        elif segment_type == "sports" and content.get("sports"):
            content_sections.append(content["sports"])
        elif segment_type == "weather" and content.get("weather"):
            content_sections.append(content["weather"])
        elif segment_type == "fun":
            if content.get("fun"):
                content_sections.append(content["fun"])
            if content.get("market"):
                content_sections.append(content["market"])

    # Build the prompt with content in the specified order
    today = datetime.now()

    # Add music content if enabled
    music_section = ""
    if include_music and content.get("music"):
        music_section = f"\n\n{content['music']}"

    user_prompt = f"""Create a {target_duration_minutes}-minute morning radio briefing script for {today.strftime('%A, %B %d, %Y')}.

Here is the content to work with (in the order you should present it):

{chr(10).join(content_sections)}{music_section}

Remember:
- Target duration: {target_duration_minutes} minutes (approximately {target_duration_minutes * 150} words)
- Follow the segment order exactly: {segment_flow}
- Prioritize the most interesting/important stories
- Make natural transitions between topics
- Include appropriate quotes with voice profiles
- End with a positive, engaging sign-off{"" if not include_music else chr(10) + "- After the sign-off, create a brief music introduction segment"}

Return ONLY the JSON script structure as specified."""

    # Call Claude (async to avoid blocking the event loop)
    message = await client.messages.create(
        model="claude-sonnet-4-20250514",  # Using Sonnet for cost efficiency
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Parse the response
    response_text = message.content[0].text

    # Try to extract JSON from the response
    try:
        # Handle potential markdown code blocks
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        script_data = json.loads(response_text.strip())
    except json.JSONDecodeError as e:
        print(f"Failed to parse Claude response as JSON: {e}")
        print(f"Response: {response_text[:500]}...")
        # Create a fallback script
        script_data = {
            "segments": [
                {
                    "type": "intro",
                    "items": [
                        {
                            "voice": "host",
                            "text": f"Good morning! It's {today.strftime('%A, %B %d, %Y')}, and this is your Morning Drive briefing.",
                        }
                    ],
                },
                {
                    "type": "outro",
                    "items": [
                        {
                            "voice": "host",
                            "text": "That's all for today's Morning Drive. Have a great day!",
                        }
                    ],
                },
            ]
        }

    # Convert to BriefingScript model
    segments = []
    for seg in script_data.get("segments", []):
        items = []
        for item in seg.get("items", []):
            items.append(
                ScriptSegmentItem(
                    voice=item.get("voice", "host"),
                    voice_profile=item.get("voice_profile"),
                    text=item.get("text", ""),
                    attribution=item.get("attribution"),
                )
            )
        segments.append(
            ScriptSegment(
                type=seg.get("type", "unknown"),
                items=items,
            )
        )

    return BriefingScript(
        date=today.strftime("%Y-%m-%d"),
        target_duration_minutes=target_duration_minutes,
        segments=segments,
    )


async def update_briefing_status(briefing_id: int, status: str):
    """Update the status of a briefing in the database."""
    async with async_session() as session:
        result = await session.execute(
            select(Briefing).where(Briefing.id == briefing_id)
        )
        briefing = result.scalar_one_or_none()
        if briefing:
            briefing.status = status
            await session.commit()


async def add_generation_error(
    briefing_id: int,
    phase: str,
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
                "phase": phase,
                "component": component,
                "message": message,
                "recoverable": recoverable,
                "fallback_description": fallback_description,
            })
            briefing.generation_errors = errors
            await session.commit()


async def request_user_confirmation(
    briefing_id: int,
    phase: str,
    component: str,
    message: str,
    fallback_description: str,
    options: list[str] = None,
) -> str:
    """
    Pause generation and wait for user to decide how to handle an error.

    Returns the user's decision: "continue", "cancel", or "retry"
    """
    import uuid

    action_id = str(uuid.uuid4())[:8]

    async with async_session() as session:
        result = await session.execute(
            select(Briefing).where(Briefing.id == briefing_id)
        )
        briefing = result.scalar_one_or_none()
        if not briefing:
            raise ValueError(f"Briefing {briefing_id} not found")

        # Record the error
        errors = briefing.generation_errors or []
        errors.append({
            "phase": phase,
            "component": component,
            "message": message,
            "recoverable": True,
            "fallback_description": fallback_description,
        })
        briefing.generation_errors = errors

        # Set pending action
        briefing.pending_action = {
            "action_id": action_id,
            "error": {
                "phase": phase,
                "component": component,
                "message": message,
                "recoverable": True,
                "fallback_description": fallback_description,
            },
            "options": options or ["continue", "cancel"],
        }
        briefing.status = "awaiting_confirmation"
        await session.commit()

    print(f"[Briefing {briefing_id}] Awaiting user confirmation for {component} error")
    print(f"  Error: {message}")
    print(f"  Fallback: {fallback_description}")

    # Poll for user response (with timeout)
    max_wait_seconds = 300  # 5 minutes
    poll_interval = 2  # seconds
    elapsed = 0

    while elapsed < max_wait_seconds:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        async with async_session() as session:
            result = await session.execute(
                select(Briefing).where(Briefing.id == briefing_id)
            )
            briefing = result.scalar_one_or_none()

            if not briefing:
                raise ValueError(f"Briefing {briefing_id} not found")

            # Check if user has responded
            if briefing.pending_action and briefing.pending_action.get("resolved"):
                decision = briefing.pending_action.get("decision", "cancel")
                # Clear the pending action
                briefing.pending_action = None
                await session.commit()
                print(f"[Briefing {briefing_id}] User decision: {decision}")
                return decision

            # Check if status changed (e.g., cancelled externally)
            if briefing.status == "cancelled":
                return "cancel"

    # Timeout - treat as cancel
    print(f"[Briefing {briefing_id}] Confirmation timeout, cancelling")
    await update_briefing_status(briefing_id, "cancelled")
    return "cancel"


async def generate_briefing_task(
    briefing_id: int,
    override_duration: Optional[int] = None,
    override_topics: Optional[list[str]] = None,
):
    """Background task to generate a complete briefing.

    This is the main entry point called by the API route.
    Errors are tracked and the user is prompted to decide how to proceed.
    """
    collected_errors = []

    try:
        # Get user settings
        async with async_session() as session:
            result = await session.execute(select(UserSettings).limit(1))
            user_settings = result.scalar_one_or_none()

            if not user_settings:
                await add_generation_error(
                    briefing_id, "setup", "settings",
                    "User settings not found", recoverable=False
                )
                await update_briefing_status(briefing_id, "failed")
                return

        # Apply overrides
        duration = override_duration or user_settings.duration_minutes
        if override_topics:
            user_settings.news_topics = override_topics

        # Phase 1: Gather content
        await update_briefing_status(briefing_id, "gathering_content")
        include_music_enabled = user_settings.include_music or False

        try:
            content = await gather_all_content(user_settings, include_music_enabled)
        except Exception as e:
            decision = await request_user_confirmation(
                briefing_id,
                phase="gathering_content",
                component="content_sources",
                message=f"Failed to gather content: {str(e)}",
                fallback_description="Cannot continue without content. Please retry or cancel.",
                options=["retry", "cancel"],
            )
            if decision == "cancel":
                return
            elif decision == "retry":
                # Retry content gathering
                content = await gather_all_content(user_settings, include_music_enabled)

        # Check for content issues
        if content.get("news") == "News unavailable.":
            await add_generation_error(
                briefing_id, "gathering_content", "news",
                "News sources returned no content",
                recoverable=True,
                fallback_description="Briefing will skip news segment"
            )

        # Phase 2: Generate script with Claude
        await update_briefing_status(briefing_id, "writing_script")
        segment_order = user_settings.segment_order or ["news", "sports", "weather", "fun"]

        try:
            script = await generate_script_with_claude(
                content, duration, segment_order, include_music_enabled
            )
        except Exception as e:
            decision = await request_user_confirmation(
                briefing_id,
                phase="writing_script",
                component="claude_api",
                message=f"Failed to generate script: {str(e)}",
                fallback_description="Cannot continue without a script. Please retry or cancel.",
                options=["retry", "cancel"],
            )
            if decision == "cancel":
                return
            elif decision == "retry":
                script = await generate_script_with_claude(
                    content, duration, segment_order, include_music_enabled
                )

        # Phase 3: Generate audio
        await update_briefing_status(briefing_id, "generating_audio")
        tts_provider = getattr(user_settings, 'tts_provider', None) or "elevenlabs"
        voice_id = user_settings.voice_id

        try:
            tts_result = await generate_audio_for_script(
                script,
                voice_id=voice_id,
                voice_style=user_settings.voice_style or "energetic",
                voice_speed=user_settings.voice_speed or 1.1,
                tts_provider=tts_provider,
            )
        except Exception as e:
            error_msg = str(e)
            # Check if it's a voice-specific error
            if "voice" in error_msg.lower() or "401" in error_msg or "403" in error_msg:
                decision = await request_user_confirmation(
                    briefing_id,
                    phase="generating_audio",
                    component="tts_voice",
                    message=f"Failed to use voice '{voice_id}': {error_msg}",
                    fallback_description="Continue with the default voice instead",
                    options=["continue", "cancel"],
                )
                if decision == "cancel":
                    return
                # Continue with default voice
                tts_result = await generate_audio_for_script(
                    script,
                    voice_id=None,  # Use default
                    voice_style=user_settings.voice_style or "energetic",
                    voice_speed=user_settings.voice_speed or 1.1,
                    tts_provider=tts_provider,
                )
            else:
                decision = await request_user_confirmation(
                    briefing_id,
                    phase="generating_audio",
                    component="tts",
                    message=f"TTS generation failed: {error_msg}",
                    fallback_description="Cannot continue without audio. Please retry or cancel.",
                    options=["retry", "cancel"],
                )
                if decision == "cancel":
                    return
                tts_result = await generate_audio_for_script(
                    script,
                    voice_id=voice_id,
                    voice_style=user_settings.voice_style or "energetic",
                    voice_speed=user_settings.voice_speed or 1.1,
                    tts_provider=tts_provider,
                )

        # Check for TTS errors - these are non-blocking but should be reported
        if tts_result.has_errors:
            for err in tts_result.errors:
                await add_generation_error(
                    briefing_id, "generating_audio", f"tts_{err.segment_type}",
                    f"TTS error for {err.segment_type}: {err.error}",
                    recoverable=True,
                    fallback_description=f"Segment '{err.segment_type}' may be incomplete"
                )

        if tts_result.missing_segment_types:
            # This is a significant issue - ask user
            missing = ", ".join(tts_result.missing_segment_types)
            decision = await request_user_confirmation(
                briefing_id,
                phase="generating_audio",
                component="tts_segments",
                message=f"Failed to generate audio for segments: {missing}",
                fallback_description=f"Continue without these segments: {missing}",
                options=["continue", "cancel"],
            )
            if decision == "cancel":
                return

        # Get music audio path
        music_audio_path = None
        if include_music_enabled and content.get("music_audio_path"):
            music_audio_path = content["music_audio_path"]
        elif include_music_enabled:
            await add_generation_error(
                briefing_id, "generating_audio", "music",
                "Music audio not available",
                recoverable=True,
                fallback_description="Briefing will skip music segment"
            )

        # Phase 4: Assemble final audio
        try:
            final_audio_path, duration_seconds, segments_metadata = await assemble_briefing_audio(
                briefing_id=briefing_id,
                audio_segments=tts_result.segments,
                include_intro=user_settings.include_intro_music,
                include_transitions=user_settings.include_transitions,
                music_audio_path=music_audio_path,
            )
        except Exception as e:
            decision = await request_user_confirmation(
                briefing_id,
                phase="assembling_audio",
                component="audio_mixer",
                message=f"Failed to assemble audio: {str(e)}",
                fallback_description="Cannot complete briefing. Please retry or cancel.",
                options=["retry", "cancel"],
            )
            if decision == "cancel":
                return
            # Retry assembly
            final_audio_path, duration_seconds, segments_metadata = await assemble_briefing_audio(
                briefing_id=briefing_id,
                audio_segments=tts_result.segments,
                include_intro=user_settings.include_intro_music,
                include_transitions=user_settings.include_transitions,
                music_audio_path=music_audio_path,
            )

        # Update briefing record with results
        async with async_session() as session:
            result = await session.execute(
                select(Briefing).where(Briefing.id == briefing_id)
            )
            briefing = result.scalar_one_or_none()

            if briefing:
                # Determine final status based on errors
                errors = briefing.generation_errors or []
                if errors:
                    briefing.status = "completed_with_warnings"
                else:
                    briefing.status = "completed"

                briefing.duration_seconds = duration_seconds
                briefing.audio_filename = final_audio_path.name
                briefing.script = script.model_dump()
                briefing.segments_metadata = segments_metadata
                briefing.pending_action = None  # Clear any pending action
                await session.commit()

        print(f"Briefing {briefing_id} generated successfully!")

    except Exception as e:
        print(f"Error generating briefing {briefing_id}: {e}")
        import traceback
        traceback.print_exc()

        # Record the fatal error
        await add_generation_error(
            briefing_id, "unknown", "system",
            f"Unexpected error: {str(e)}",
            recoverable=False
        )
        await update_briefing_status(briefing_id, "failed")
