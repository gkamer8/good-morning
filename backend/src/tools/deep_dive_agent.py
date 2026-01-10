"""Deep Dive Agent - Uses Anthropic's built-in web tools for research."""

from dataclasses import dataclass
from typing import Optional

from anthropic import AsyncAnthropic

from src.config import get_settings


@dataclass
class DeepDiveResult:
    """Result from deep dive research."""

    script_text: str  # The generated script segment
    user_prompt: str  # The prompt sent to the agent
    full_response: str  # Full conversation including tool uses for debugging


async def research_deep_dive(
    topic: str,
    context: str,
    url: Optional[str] = None,
    writing_style: str = "good_morning_america",
) -> DeepDiveResult:
    """Use Anthropic's built-in web tools to research and write a segment.

    Args:
        topic: Brief description of the topic to research
        context: Original context/summary from news
        url: Optional URL of the original article
        writing_style: Writing style to match (good_morning_america, firing_line, ernest_hemingway)

    Returns:
        DeepDiveResult with script text and conversation for debugging
    """
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

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

    # Writing style descriptions
    style_instructions = {
        "good_morning_america": "Write in an upbeat, energetic morning show style. Be enthusiastic and engaging.",
        "firing_line": "Write with intellectual wit and sophistication, like William F. Buckley. Be incisive and thoughtful.",
        "ernest_hemingway": "Write in a terse, direct style. Short sentences. Clear facts. No fluff.",
    }

    style_desc = style_instructions.get(writing_style, style_instructions["good_morning_america"])

    user_prompt = f"""Research this news topic and write a 2-3 minute radio script segment.

Topic: {topic}
Original context: {context}
{f'Original article URL: {url}' if url else ''}

Steps:
1. Use web_search to find current information about this topic
2. If you find promising results, use web_fetch to get full article content from the most relevant URLs
3. Synthesize the information into an engaging, conversational radio script

Writing style: {style_desc}

Requirements:
- Write in the voice of a morning radio host
- Be informative but engaging - this is radio, not a newspaper
- Include specific facts, numbers, and quotes when available
- Target length: 300-400 words (~2-3 minutes when spoken)
- Do NOT include any markup, headers, or formatting - just the spoken text
- Start directly with the content, no "Here's your segment:" preamble

Return ONLY the script text that should be spoken on air."""

    messages = [{"role": "user", "content": user_prompt}]

    # Track full conversation for debugging
    conversation_log = [f"USER:\n{user_prompt}\n"]

    # Agentic loop - keep going until we get a final text response
    max_iterations = 10
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            tools=tools,
            messages=messages,
            extra_headers={"anthropic-beta": "web-fetch-2025-09-10"},
        )

        # Log the response
        conversation_log.append(f"\nASSISTANT (stop_reason={response.stop_reason}):")

        # Check if we have tool use
        has_tool_use = False
        tool_results = []
        final_text = ""

        for block in response.content:
            if block.type == "text":
                final_text += block.text
                conversation_log.append(f"TEXT: {block.text[:500]}...")
            elif block.type == "tool_use":
                has_tool_use = True
                conversation_log.append(f"TOOL_USE: {block.name} (id={block.id})")
                if hasattr(block, "input"):
                    conversation_log.append(f"  Input: {str(block.input)[:200]}...")
            elif block.type == "server_tool_use":
                has_tool_use = True
                conversation_log.append(f"SERVER_TOOL_USE: {block.name} (id={block.id})")
                if hasattr(block, "input"):
                    conversation_log.append(f"  Input: {str(block.input)[:200]}...")
            elif block.type == "web_search_tool_result":
                conversation_log.append(f"WEB_SEARCH_RESULT: {len(getattr(block, 'content', []))} results")
            elif block.type == "web_fetch_tool_result":
                conversation_log.append(f"WEB_FETCH_RESULT: content received")

        # If stop reason is "end_turn" and we have text, we're done
        if response.stop_reason == "end_turn" and final_text:
            break

        # If we have tool use, the API handles tool execution automatically
        # for built-in tools - we just need to continue the conversation
        if has_tool_use:
            # For built-in tools, the results come back in the same response
            # We need to add the assistant message and continue
            messages.append({"role": "assistant", "content": response.content})

            # Check if there are any tool results we need to pass back
            # Built-in tools include results in the response, so we might be done
            if response.stop_reason == "end_turn":
                break
        else:
            # No tool use and no end_turn, something unexpected
            break

    # Clean up the script text - remove any preamble
    script_text = final_text.strip()

    # Remove common AI preambles if present
    preamble_patterns = [
        "Here's your segment:",
        "Here's the script:",
        "Here is the script:",
        "Script:",
    ]
    for pattern in preamble_patterns:
        if script_text.lower().startswith(pattern.lower()):
            script_text = script_text[len(pattern):].strip()

    return DeepDiveResult(
        script_text=script_text,
        user_prompt=user_prompt,
        full_response="\n".join(conversation_log),
    )
