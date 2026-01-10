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
from src.tools.deep_dive_agent import research_deep_dive
from src.prompts import (
    PromptRenderer,
    get_segment_display_names,
    get_writing_style,
    render_prompt,
)


DEFAULT_WRITING_STYLE = "good_morning_america"


async def process_deep_dive_tags(
    script: "BriefingScript",
    writing_style: str,
    prompt_renderer: PromptRenderer = None,
) -> "BriefingScript":
    """Find and replace [DEEP_DIVE] tags with researched content.

    Args:
        script: The generated script with potential [DEEP_DIVE] tags
        writing_style: Writing style to pass to deep dive agent
        prompt_renderer: Optional renderer to track prompts for storage

    Returns:
        Updated script with tags replaced by researched content
    """
    import re

    # Pattern to match [DEEP_DIVE topic="..." context="..." url="..."]
    tag_pattern = r'\[DEEP_DIVE topic="([^"]+)" context="([^"]+)"(?: url="([^"]+)")?\]'

    deep_dive_index = 0

    for segment in script.segments:
        for item in segment.items:
            matches = list(re.finditer(tag_pattern, item.text))

            if not matches:
                continue

            # Process each tag in this item
            new_text = item.text
            for match in matches:
                topic = match.group(1)
                context = match.group(2)
                url = match.group(3)  # May be None

                deep_dive_index += 1
                print(f"[Deep Dive {deep_dive_index}] Researching: {topic}")

                try:
                    result = await research_deep_dive(
                        topic=topic,
                        context=context,
                        url=url,
                        writing_style=writing_style,
                    )

                    # Store conversation in prompt_renderer for admin panel viewing
                    if prompt_renderer:
                        prompt_renderer.add_prompt(
                            f"deep_dive_{deep_dive_index}_prompt",
                            result.user_prompt
                        )
                        prompt_renderer.add_prompt(
                            f"deep_dive_{deep_dive_index}_response",
                            result.full_response
                        )

                    # Replace the tag with the generated content
                    new_text = new_text.replace(match.group(0), result.script_text)
                    print(f"[Deep Dive {deep_dive_index}] Generated {len(result.script_text)} chars")

                except Exception as e:
                    print(f"[Deep Dive {deep_dive_index}] Error: {e}")
                    # On error, replace tag with fallback using the original context
                    fallback = f"Now, about {topic}. {context}"
                    new_text = new_text.replace(match.group(0), fallback)

                    if prompt_renderer:
                        prompt_renderer.add_prompt(
                            f"deep_dive_{deep_dive_index}_error",
                            str(e)
                        )

            item.text = new_text

    return script


async def generate_briefing_title(
    script: BriefingScript,
    user_timezone: str = None,
    prompt_renderer: PromptRenderer = None,
) -> str:
    """Generate a brief, descriptive title for the briefing based on its content.

    Args:
        script: The generated briefing script
        user_timezone: IANA timezone string for date formatting
        prompt_renderer: Optional renderer to track prompts for storage
    """
    from src.utils.timezone import get_user_now

    settings = get_settings()
    today = get_user_now(user_timezone)
    date_str = today.strftime("%-m/%-d/%y")  # m/d/yy format

    # Extract text from all segments to summarize
    all_text = []
    for segment in script.segments:
        for item in segment.items:
            all_text.append(item.text[:200])  # First 200 chars of each item

    content_summary = " ".join(all_text)[:1500]  # Limit total content

    # Render prompt from template
    user_prompt = render_prompt(
        "briefing_title.jinja2",
        content_summary=content_summary,
    )

    # Track rendered prompt if renderer provided
    if prompt_renderer:
        prompt_renderer.add_prompt("title_prompt", user_prompt)

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[{"role": "user", "content": user_prompt}]
        )
        topic_words = response.content[0].text.strip()
        # Clean up any extra punctuation or quotes
        topic_words = topic_words.strip('"\'.,')
        return f"{date_str} - {topic_words}"
    except Exception as e:
        print(f"Failed to generate title: {e}")
        return f"{date_str} - Morning Briefing"


async def gather_all_content(
    settings: UserSettings,
    include_music: bool = False,
    length_mode: str = "short",
    user_timezone: str = None,
) -> dict:
    """Gather content from all sources in parallel.

    Args:
        settings: User settings
        include_music: Whether to include music segment
        length_mode: "short" or "long" - controls content limits
        user_timezone: IANA timezone string for date/time operations
    """
    from src.api.schemas import CONTENT_LIMITS
    from src.utils.timezone import get_user_now

    limits = CONTENT_LIMITS.get(length_mode, CONTENT_LIMITS["short"])
    print(f"[Content] gather_all_content: length_mode={length_mode!r}, limits.history_events={limits.history_events}")

    # Prepare tasks
    async def fetch_news():
        articles = await get_top_news(
            sources=settings.news_sources or ["bbc", "npr", "nyt"],
            topics=settings.news_topics or ["top", "technology", "business"],
            limit=10,
            stories_per_source=limits.news_stories_per_source,
        )
        return format_news_for_agent(articles)

    async def fetch_sports():
        leagues = settings.sports_leagues or ["nfl", "mlb", "nhl"]
        teams = settings.sports_teams or []

        scores = await get_scores_for_leagues(
            leagues,
            favorite_teams_only=limits.sports_favorite_teams_only,
            favorite_teams=teams,
        )
        news = await get_sports_news(leagues, limit_per_league=2)
        team_games = await get_team_updates(teams) if teams else []

        return format_sports_for_agent(
            scores, news, team_games, favorite_teams=teams
        )

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
        content = await get_fun_content(
            segments,
            history_limit=limits.history_events,
            user_timezone=user_timezone,
        )
        return format_fun_content_for_agent(content, user_timezone=user_timezone)

    async def fetch_market():
        if "market_minute" in (settings.fun_segments or []):
            summary = await get_market_summary(
                movers_limit=limits.finance_movers_limit,
                user_timezone=user_timezone,
            )
            return format_market_for_agent(summary, user_timezone=user_timezone)
        return ""

    async def fetch_music():
        if include_music:
            today = get_user_now(user_timezone).strftime("%Y-%m-%d")

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


async def generate_script_with_claude(
    content: dict,
    length_mode: str,
    segment_order: list[str] = None,
    include_music: bool = False,
    writing_style: str = None,
    user_timezone: str = None,
    prompt_renderer: PromptRenderer = None,
    news_exclusions: list[str] = None,
    deep_dive_count: int = 0,
) -> BriefingScript:
    """Use Claude to generate the radio script.

    Args:
        content: Content dict from gather_all_content
        length_mode: "short" or "long" - determines target duration and word count
        segment_order: Order of segments
        include_music: Whether to include music segment
        writing_style: Writing style key
        user_timezone: IANA timezone string for date/time operations
        prompt_renderer: Optional renderer to track prompts for storage
        news_exclusions: Topics to exclude from news segment (not history or other segments)
        deep_dive_count: Number of stories to mark for deep dive research (0 = disabled)
    """
    from src.api.schemas import CONTENT_LIMITS
    from src.utils.timezone import get_user_now

    limits = CONTENT_LIMITS.get(length_mode, CONTENT_LIMITS["short"])
    target_duration_minutes = limits.target_duration_minutes
    target_word_count = limits.target_word_count

    settings = get_settings()

    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Use default order if not provided
    if not segment_order:
        segment_order = ["news", "sports", "weather", "fun"]

    # Build the segment flow string for the prompt using YAML data
    segment_display_names = get_segment_display_names()
    segment_names = [segment_display_names.get(s, s.title()) for s in segment_order]
    segment_flow = " → ".join(segment_names) + " → Sign off"

    # Get writing style instructions from YAML
    style_key = writing_style or DEFAULT_WRITING_STYLE
    style_config = get_writing_style(style_key)
    writing_style_instructions = style_config["prompt"]

    # Render system prompt from Jinja template
    system_prompt = render_prompt(
        "script_writer_system.jinja2",
        writing_style_instructions=writing_style_instructions,
        segment_flow=segment_flow,
        include_music=include_music,
        news_exclusions=news_exclusions or [],
        deep_dive_count=deep_dive_count,
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
    today = get_user_now(user_timezone)

    # Add music content if enabled
    music_section = ""
    if include_music and content.get("music"):
        music_section = content["music"]

    # Render user prompt from Jinja template
    user_prompt = render_prompt(
        "script_writer_user.jinja2",
        target_duration_minutes=target_duration_minutes,
        target_word_count=target_word_count,
        date_formatted=today.strftime('%A, %B %d, %Y'),
        content_sections="\n".join(content_sections),
        music_section=music_section,
        segment_flow=segment_flow,
        include_music=include_music,
    )

    # Track rendered prompts if renderer provided
    if prompt_renderer:
        prompt_renderer.add_prompt("script_system_prompt", system_prompt)
        prompt_renderer.add_prompt("script_user_prompt", user_prompt)

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
    override_length: Optional[str] = None,
    override_topics: Optional[list[str]] = None,
):
    """Background task to generate a complete briefing.

    This is the main entry point called by the API route.
    Errors are tracked and the user is prompted to decide how to proceed.

    Args:
        briefing_id: ID of the briefing record to update
        override_length: Override briefing length ("short" or "long")
        override_topics: Override news topics
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
        db_briefing_length = getattr(user_settings, 'briefing_length', None)
        print(f"[Briefing {briefing_id}] DB briefing_length: {db_briefing_length!r}, override_length: {override_length!r}")

        # Use override if provided, otherwise fall back to DB setting, then default to "short"
        length_mode = override_length or db_briefing_length or "short"
        print(f"[Briefing {briefing_id}] Final length_mode: {length_mode!r}")

        if override_topics:
            user_settings.news_topics = override_topics

        # Get user timezone for all date/time operations
        user_timezone = getattr(user_settings, 'timezone', None) or "America/New_York"

        # Create prompt renderer to track all rendered prompts
        prompt_renderer = PromptRenderer()

        # Phase 1: Gather content
        await update_briefing_status(briefing_id, "gathering_content")
        include_music_enabled = user_settings.include_music or False

        try:
            content = await gather_all_content(
                user_settings, include_music_enabled, length_mode, user_timezone=user_timezone
            )
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
                content = await gather_all_content(
                    user_settings, include_music_enabled, length_mode, user_timezone=user_timezone
                )

        # Check for content issues
        if content.get("news") == "News unavailable.":
            await add_generation_error(
                briefing_id, "gathering_content", "news",
                "News sources returned no content",
                recoverable=True,
                fallback_description="Briefing will skip news segment"
            )

        if content.get("weather") == "Weather unavailable.":
            await add_generation_error(
                briefing_id, "gathering_content", "weather",
                "Weather API returned no content or timed out",
                recoverable=True,
                fallback_description="Briefing will have generic weather fallback"
            )

        if content.get("sports") == "Sports unavailable.":
            await add_generation_error(
                briefing_id, "gathering_content", "sports",
                "Sports API returned no content",
                recoverable=True,
                fallback_description="Briefing will skip sports segment"
            )

        # Phase 2: Generate script with Claude
        await update_briefing_status(briefing_id, "writing_script")
        segment_order = user_settings.segment_order or ["news", "sports", "weather", "fun"]
        writing_style = getattr(user_settings, 'writing_style', None) or DEFAULT_WRITING_STYLE

        news_exclusions = getattr(user_settings, 'news_exclusions', None) or []

        # Calculate deep dive count based on user setting and length mode
        deep_dive_enabled = getattr(user_settings, 'deep_dive_enabled', False)
        if deep_dive_enabled:
            deep_dive_count = 1 if length_mode == "short" else 2
            print(f"[Briefing {briefing_id}] Deep dive enabled: {deep_dive_count} stories")
        else:
            deep_dive_count = 0

        try:
            script = await generate_script_with_claude(
                content, length_mode, segment_order, include_music_enabled, writing_style,
                user_timezone=user_timezone,
                prompt_renderer=prompt_renderer,
                news_exclusions=news_exclusions,
                deep_dive_count=deep_dive_count,
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
                    content, length_mode, segment_order, include_music_enabled, writing_style,
                    user_timezone=user_timezone,
                    prompt_renderer=prompt_renderer,
                    news_exclusions=news_exclusions,
                    deep_dive_count=deep_dive_count,
                )

        # Post-process: expand any [DEEP_DIVE] tags with web research
        if deep_dive_count > 0:
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
                    briefing_id, "writing_script", "deep_dive",
                    f"Deep dive research failed: {str(e)}",
                    recoverable=True,
                    fallback_description="Deep dive stories will use basic coverage"
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

        # Generate a descriptive title based on the script content
        briefing_title = await generate_briefing_title(
            script, user_timezone=user_timezone, prompt_renderer=prompt_renderer
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

                briefing.title = briefing_title
                briefing.duration_seconds = duration_seconds
                briefing.audio_filename = final_audio_path.name
                briefing.script = script.model_dump()
                briefing.segments_metadata = segments_metadata
                briefing.pending_action = None  # Clear any pending action
                briefing.rendered_prompts = prompt_renderer.get_all_rendered()
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
