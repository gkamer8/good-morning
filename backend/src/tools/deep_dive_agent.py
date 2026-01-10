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
        conversation_log.append(f"\n{'='*60}")
        conversation_log.append(f"ASSISTANT (iteration={iteration}, stop_reason={response.stop_reason}):")
        conversation_log.append(f"{'='*60}")

        # Check if we have tool use
        has_tool_use = False
        tool_results = []
        final_text = ""

        for block in response.content:
            if block.type == "text":
                final_text += block.text
                conversation_log.append(f"\n[TEXT OUTPUT]")
                conversation_log.append(block.text)

            elif block.type == "tool_use":
                has_tool_use = True
                conversation_log.append(f"\n[TOOL_USE: {block.name}]")
                if hasattr(block, "input") and block.input:
                    conversation_log.append(f"Input: {block.input}")

            elif block.type == "server_tool_use":
                has_tool_use = True
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
                conversation_log.append(f"\n[WEB_FETCH_RESULT]")
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
                    conversation_log.append(f"  (No content received)")

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
