"""Deep Dive Agent - Uses Anthropic's built-in web tools for research."""

from dataclasses import dataclass
from typing import Optional

from anthropic import AsyncAnthropic

from src.api.schemas import CLAUDE_MODEL, DEFAULT_WRITING_STYLE
from src.config import get_settings
from src.prompts import get_writing_style, render_prompt

MAX_DEEP_DIVE_TOKENS = 2000

@dataclass
class DeepDiveResult:
    """Result from deep dive research."""

    script_text: str  # The generated script segment
    user_prompt: str  # The prompt sent to the agent
    full_response: str  # Full conversation including tool uses for debugging


async def get_deep_dive_script_from_api(
    system_prompt: str,
    user_prompt: str,
    conversation_log: list[str],  # For debugging from the admin panel
) -> str | None:
    """
    Interact with the Anthopic API to create a dive dive script
    
    Failures will either raise an exception or return None.

    If the stop reason is anything other than end_turn, will return None.
    """
    
    # Initial user message
    messages = [{"role": "user", "content": user_prompt}]
    
    # Built-in tool definitions - Anthropic handles execution server-side
    tools = [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,  # Limit searches per deep dive
        },
        {
            "type": "web_fetch_20250910",
            "name": "web_fetch",
            "max_uses": 2,  # Limit fetches per deep dive
        },
    ]

    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    # We use the messages API
    response = await client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_DEEP_DIVE_TOKENS,
        system=system_prompt,
        tools=tools,
        messages=messages,
        extra_headers={"anthropic-beta": "web-fetch-2025-09-10"},
    )

    # Log the response
    conversation_log.append(f"\n{'='*60}")
    conversation_log.append("ASSISTANT:")
    conversation_log.append(f"{'='*60}")

    text = None

    if response.stop_reason != "end_turn":
        # Something went wrong, like Claude called a fictitious tool
        # (note that we're using only server tools that won't cause a stop)
        return None

    for block in response.content:
        if block.type == "text":
            conversation_log.append("\n[TEXT OUTPUT]")
            conversation_log.append(block.text)
            # Text gets overwritten each time so we only collect the final text
            text = block.text
        elif block.type == "server_tool_use":
            tool_input = getattr(block, "input", {}) or {}
            conversation_log.append(f"\n[SERVER_TOOL_USE: {block.name}]")
            if block.name == "web_search" and tool_input:
                query = tool_input.get("query", "")
                conversation_log.append(f"  Search Query: \"{query}\"")
            elif block.name == "web_fetch" and tool_input:
                url = tool_input.get("url", "")
                conversation_log.append(f"  Fetching URL: {url}")
            else:
                conversation_log.append(f"  Input: {tool_input}")
        elif block.type == "web_search_tool_result":
            content = getattr(block, "content", []) or []
            conversation_log.append(f"\n[WEB_SEARCH_RESULTS: {len(content)} results]")
            for i, result in enumerate(content[:10]):  # Show up to 10 results
                if hasattr(result, "type"):
                    if result.type == "web_search_result":
                        title = getattr(result, "title", "")
                        url = getattr(result, "url", "")
                        snippet = getattr(result, "snippet", "")[:200] if hasattr(result, "snippet") else ""
                        conversation_log.append(f"  {i+1}. {title}")
                        conversation_log.append(f"     URL: {url}")
                        if snippet:
                            conversation_log.append(f"     Snippet: {snippet}...")
        elif block.type == "web_fetch_tool_result":
            content = getattr(block, "content", None)
            conversation_log.append("\n[WEB_FETCH_RESULT]")
            if content:
                # Try to get text length
                if isinstance(content, str):
                    conversation_log.append(f"  Content length: {len(content)} chars")
                    conversation_log.append(f"  Preview: {content[:500]}...")
                elif isinstance(content, list):
                    conversation_log.append(f"  Content blocks: {len(content)}")
                    for item in content[:3]:
                        if hasattr(item, "text"):
                            conversation_log.append(f"  Preview: {item.text[:300]}...")
                            break
            else:
                conversation_log.append("  (No content received)")
        else:
            conversation_log.append(f"\nUNKNOWN BLOCK TYPE {block.type}")

    return text

async def research_deep_dive(
    topic: str,
    context: str,
    url: Optional[str] = None,
    writing_style: str = DEFAULT_WRITING_STYLE,
    script_before: str = "",
    script_after: str = "",
) -> DeepDiveResult:
    """Use Anthropic's built-in web tools to research and write a segment.

    Args:
        topic: Brief description of the topic to research
        context: Original context/summary from news
        url: Optional URL of the original article
        writing_style: Writing style to match (good_morning_america, firing_line, ernest_hemingway)
        script_before: The script text that comes before this deep dive (for context/tone matching)
        script_after: The script text that comes after this deep dive (for continuity)

    Returns:
        DeepDiveResult with script text and conversation for debugging
    """

    # Get writing style from YAML config
    style_config = get_writing_style(writing_style)
    writing_style_instructions = style_config["prompt"]

    # Build context previews for the template
    script_before_preview = script_before[-800:] if len(script_before) > 800 else script_before
    script_after_preview = script_after[:500] if len(script_after) > 500 else script_after

    system_prompt = render_prompt(
        "deep_dive_system.jinja2",
        writing_style_instructions=writing_style_instructions,
    )

    user_prompt = render_prompt(
        "deep_dive_user.jinja2",
        topic=topic,
        context=context,
        url=url,
        script_before=script_before,
        script_after=script_after,
        script_before_preview=script_before_preview,
        script_after_preview=script_after_preview,
    )

    # Track full conversation for debugging
    conversation_log = [f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}\n"]

    # Give it 2 chances
    max_iterations = 2
    final_text = ""
    for i in range(max_iterations):
        text = await get_deep_dive_script_from_api(system_prompt, user_prompt, conversation_log)
        if text:
            final_text = text
            break
        else:
            conversation_log.append(f"\nDID NOT GET FINAL TEXT ON ITERATION {i+1}/{max_iterations}; DOING ANOTHER ITERATION")

    # Clean up the script text - remove any preamble
    script_text = final_text.strip()

    return DeepDiveResult(
        script_text=script_text,
        user_prompt=user_prompt,
        full_response="\n".join(conversation_log),
    )
