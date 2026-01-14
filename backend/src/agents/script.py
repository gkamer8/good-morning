"""Script generation and processing functions."""

import json
import re

from anthropic import AsyncAnthropic

from src.api.schemas import (
    BriefingScript,
    CLAUDE_MODEL,
    CONTENT_LIMITS,
    DEFAULT_SEGMENT_ORDER,
    DEFAULT_VOICE,
    DEFAULT_WRITING_STYLE,
    LengthMode,
    ScriptSegment,
    ScriptSegmentItem,
)
from src.config import get_settings
from src.prompts import (
    PromptRenderer,
    get_segment_display_names,
    get_writing_style,
    render_prompt,
)
from src.tools.deep_dive_agent import research_deep_dive
from src.utils.timezone import get_user_now


def _collect_script_text(script: BriefingScript, up_to_segment_idx: int, up_to_item_idx: int, up_to_char: int = None) -> str:
    """Collect all script text up to a specific point."""
    texts = []
    for seg_idx, segment in enumerate(script.segments):
        for item_idx, item in enumerate(segment.items):
            if seg_idx < up_to_segment_idx:
                texts.append(item.text)
            elif seg_idx == up_to_segment_idx:
                if item_idx < up_to_item_idx:
                    texts.append(item.text)
                elif item_idx == up_to_item_idx and up_to_char is not None:
                    texts.append(item.text[:up_to_char])
    return "\n\n".join(texts)


def _collect_script_text_after(script: BriefingScript, from_segment_idx: int, from_item_idx: int, from_char: int = None) -> str:
    """Collect all script text after a specific point."""
    texts = []
    for seg_idx, segment in enumerate(script.segments):
        for item_idx, item in enumerate(segment.items):
            if seg_idx > from_segment_idx:
                texts.append(item.text)
            elif seg_idx == from_segment_idx:
                if item_idx > from_item_idx:
                    texts.append(item.text)
                elif item_idx == from_item_idx and from_char is not None:
                    texts.append(item.text[from_char:])
    return "\n\n".join(texts)


async def process_deep_dive_tags(
    script: BriefingScript,
    writing_style: str,
    prompt_renderer: PromptRenderer = None,
) -> BriefingScript:
    """Find and replace [DEEP_DIVE] tags with researched content.

    Args:
        script: The generated script with potential [DEEP_DIVE] tags
        writing_style: Writing style to pass to deep dive agent
        prompt_renderer: Optional renderer to track prompts for storage

    Returns:
        Updated script with tags replaced by researched content
    """
    tag_pattern = r'\[DEEP_DIVE topic="([^"]+)" context="([^"]+)"(?: url="([^"]+)")?\]'
    deep_dive_index = 0

    for seg_idx, segment in enumerate(script.segments):
        for item_idx, item in enumerate(segment.items):
            matches = list(re.finditer(tag_pattern, item.text))

            if not matches:
                continue

            new_text = item.text
            for match in matches:
                topic = match.group(1)
                context = match.group(2)
                url = match.group(3)

                deep_dive_index += 1
                print(f"[Deep Dive {deep_dive_index}] Researching: {topic}")

                script_before = _collect_script_text(script, seg_idx, item_idx, match.start())
                text_before_tag = new_text[:match.start()]
                if text_before_tag.strip():
                    script_before = script_before + "\n\n" + text_before_tag if script_before else text_before_tag

                text_after_tag = new_text[match.end():]
                script_after = _collect_script_text_after(script, seg_idx, item_idx, match.end())
                if text_after_tag.strip():
                    script_after = text_after_tag + "\n\n" + script_after if script_after else text_after_tag

                try:
                    result = await research_deep_dive(
                        topic=topic,
                        context=context,
                        url=url,
                        writing_style=writing_style,
                        script_before=script_before,
                        script_after=script_after,
                    )

                    if prompt_renderer:
                        prompt_renderer.add_prompt(f"deep_dive_{deep_dive_index}_prompt", result.user_prompt)
                        prompt_renderer.add_prompt(f"deep_dive_{deep_dive_index}_response", result.full_response)

                    new_text = new_text.replace(match.group(0), result.script_text)
                    print(f"[Deep Dive {deep_dive_index}] Generated {len(result.script_text)} chars")

                except Exception as e:
                    print(f"[Deep Dive {deep_dive_index}] Error: {e}")
                    fallback = f"Now, about {topic}. {context}"
                    new_text = new_text.replace(match.group(0), fallback)

                    if prompt_renderer:
                        prompt_renderer.add_prompt(f"deep_dive_{deep_dive_index}_error", str(e))

            item.text = new_text

    return script


async def generate_briefing_title(
    script: BriefingScript,
    user_timezone: str = None,
    prompt_renderer: PromptRenderer = None,
) -> str:
    """Generate a brief, descriptive title for the briefing based on its content."""
    settings = get_settings()
    today = get_user_now(user_timezone)
    date_str = today.strftime("%-m/%-d/%y")

    all_text = []
    for segment in script.segments:
        for item in segment.items:
            all_text.append(item.text[:200])

    content_summary = " ".join(all_text)[:1500]

    user_prompt = render_prompt(
        "briefing_title.jinja2",
        content_summary=content_summary,
    )

    if prompt_renderer:
        prompt_renderer.add_prompt("title_prompt", user_prompt)

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=50,
        messages=[{"role": "user", "content": user_prompt}]
    )
    topic_words = response.content[0].text.strip()
    topic_words = topic_words.strip('"\'.,')
    return f"{date_str} - {topic_words}"


async def generate_script_with_claude(
    content: dict,
    length_mode: LengthMode,
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
        length_mode: LengthMode.SHORT or LengthMode.LONG - determines target duration and word count
        segment_order: Order of segments
        include_music: Whether to include music segment
        writing_style: Writing style key
        user_timezone: IANA timezone string for date/time operations
        prompt_renderer: Optional renderer to track prompts for storage
        news_exclusions: Topics to exclude from news segment (not history or other segments)
        deep_dive_count: Number of stories to mark for deep dive research (0 = disabled)
    """
    limits = CONTENT_LIMITS.get(length_mode, CONTENT_LIMITS[LengthMode.SHORT])
    target_duration_minutes = limits.target_duration_minutes
    target_word_count = limits.target_word_count

    settings = get_settings()

    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    if not segment_order:
        segment_order = DEFAULT_SEGMENT_ORDER

    segment_display_names = get_segment_display_names()
    segment_names = [segment_display_names.get(s, s.title()) for s in segment_order]
    segment_flow = " → ".join(segment_names) + " → Sign off"

    style_key = writing_style or DEFAULT_WRITING_STYLE
    style_config = get_writing_style(style_key)
    writing_style_instructions = style_config["prompt"]

    system_prompt = render_prompt(
        "script_writer_system.jinja2",
        writing_style_instructions=writing_style_instructions,
        segment_flow=segment_flow,
        include_music=include_music,
        news_exclusions=news_exclusions or [],
        deep_dive_count=deep_dive_count,
    )

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

    today = get_user_now(user_timezone)

    music_section = ""
    if include_music and content.get("music"):
        music_section = content["music"]

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

    if prompt_renderer:
        prompt_renderer.add_prompt("script_system_prompt", system_prompt)
        prompt_renderer.add_prompt("script_user_prompt", user_prompt)

    message = await client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    response_text = message.content[0].text

    try:
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        script_data = json.loads(response_text.strip())
    except json.JSONDecodeError as e:
        print(f"Failed to parse Claude response as JSON: {e}")
        print(f"Response: {response_text[:500]}...")
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

    segments = []
    for seg in script_data.get("segments", []):
        items = []
        for item in seg.get("items", []):
            items.append(
                ScriptSegmentItem(
                    voice=item.get("voice", DEFAULT_VOICE),
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

