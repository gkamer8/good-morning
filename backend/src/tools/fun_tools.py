"""Fun segment tools - This Day in History, quotes, trivia, etc."""

import re
from dataclasses import dataclass
from typing import Optional

import feedparser
import httpx

from src.utils.timezone import get_user_now


@dataclass
class HistoricalEvent:
    """A historical event."""

    year: int
    description: str
    category: str  # event, birth, death


@dataclass
class Quote:
    """An inspirational quote."""

    text: str
    author: str
    category: Optional[str] = None


@dataclass
class DadJoke:
    """A dad joke."""

    setup: str
    punchline: Optional[str] = None  # Some jokes are one-liners


@dataclass
class WordOfTheDay:
    """Word of the day."""

    word: str
    part_of_speech: str
    definition: str
    example: Optional[str] = None
    pronunciation: Optional[str] = None


# Wikipedia API for historical events
WIKIPEDIA_API = "https://en.wikipedia.org/api/rest_v1/feed/onthisday"

# User-Agent is required by Wikipedia API
USER_AGENT = "MorningDrive/1.0 (Personal Morning Briefing App; gkamer@example.com)"


async def fetch_this_day_in_history(
    user_timezone: str,
    max_events: int = 5
) -> list[HistoricalEvent]:
    """Fetch events that happened on this day in history.

    Args:
        user_timezone: IANA timezone string for determining "today"
        max_events: Max number of historical events to return
    """
    now = get_user_now(user_timezone)
    # Wikipedia API requires zero-padded month and day
    month = f"{now.month:02d}"
    day = f"{now.day:02d}"

    events = []

    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        # Fetch all types
        response = await client.get(f"{WIKIPEDIA_API}/all/{month}/{day}")
        response.raise_for_status()
        data = response.json()

    # Selected events
    selected = data.get("selected", [])
    for item in selected[:max_events]:
        events.append(
            HistoricalEvent(
                year=item.get("year", 0),
                description=item.get("text", ""),
                category="event",
            )
        )

    return events


async def fetch_quote_of_the_day() -> Optional[Quote]:
    """Fetch an inspirational quote."""
    # Using ZenQuotes API (free, no key required)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get("https://zenquotes.io/api/today")
        response.raise_for_status()
        data = response.json()

    quote_data = data[0]
    return Quote(
        text=quote_data.get("q", ""),
        author=quote_data.get("a", "Unknown"),
    )


async def fetch_dad_joke() -> Optional[DadJoke]:
    """Fetch a random dad joke."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            "https://icanhazdadjoke.com/",
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

    return DadJoke(
        setup=data.get("joke", ""),
        punchline=None,  # This API returns one-liner jokes
    )


async def fetch_word_of_the_day(user_timezone: str = None) -> Optional[WordOfTheDay]:
    """Fetch word of the day from Merriam-Webster RSS feed.

    Args:
        user_timezone: IANA timezone string (unused, kept for API compatibility)
    """
    _ = user_timezone  # Kept for API compatibility

    MERRIAM_WEBSTER_RSS = "https://www.merriam-webster.com/wotd/feed/rss2"

    # feedparser can fetch and parse in one step
    feed = feedparser.parse(MERRIAM_WEBSTER_RSS)

    if not feed.entries:
        return None

    entry = feed.entries[0]  # Today's word is the first entry

    word = entry.get("title", "").strip()
    definition = entry.get("merriam_shortdef", "").strip()
    description = entry.get("summary", "")

    # Parse pronunciation (pattern: \ih-LISS-it\)
    pronunciation = None
    pron_match = re.search(r"\\([^\\]+)\\", description)
    if pron_match:
        pronunciation = pron_match.group(1).strip()

    # Parse part of speech (comes after pronunciation, in <em> tags before <br />)
    part_of_speech = ""
    pos_match = re.search(r"<em>(\w+)</em>\s*<br", description)
    if pos_match:
        part_of_speech = pos_match.group(1).strip()

    # Parse example (lines starting with //)
    example = None
    example_match = re.search(r"//\s*([^<]+)<", description)
    if example_match:
        example = example_match.group(1).strip()

    if word:
        return WordOfTheDay(
            word=word,
            part_of_speech=part_of_speech,
            definition=definition,
            example=example,
            pronunciation=pronunciation,
        )

    return None


async def fetch_sports_history(user_timezone: str = "UTC") -> list[HistoricalEvent]:
    """Fetch sports events that happened on this day."""
    # This would ideally use a sports history API
    # For now, we'll rely on the Wikipedia API and filter
    events = await fetch_this_day_in_history(user_timezone=user_timezone, max_events=10)

    # Simple keyword filter for sports-related events
    sports_keywords = [
        "world series", "super bowl", "olympics", "championship", "world cup",
        "nfl", "nba", "mlb", "nhl", "tennis", "golf", "boxing", "wrestling",
        "marathon", "race", "tournament", "medal", "record", "athlete",
        "baseball", "football", "basketball", "hockey", "soccer",
    ]

    sports_events = []
    for event in events:
        desc_lower = event.description.lower()
        if any(keyword in desc_lower for keyword in sports_keywords):
            sports_events.append(event)

    return sports_events[:3]


async def get_fun_content(
    segments: list[str],
    history_limit: Optional[int] = None,
    user_timezone: str = None,
) -> dict[str, any]:
    """Fetch fun content for requested segment types.

    Args:
        segments: List of segment types to include:
            - this_day_in_history
            - quote_of_the_day
            - dad_joke
            - word_of_the_day
            - sports_history
            - market_minute (handled separately)
        history_limit: If set, limit This Day in History to N events total
        user_timezone: IANA timezone string for date-dependent content

    Returns:
        Dict with content for each segment type
    """
    print(f"[Fun Content] get_fun_content called with history_limit={history_limit!r}")
    content = {}

    for segment in segments:
        if segment == "this_day_in_history":
            events = await fetch_this_day_in_history(
                user_timezone=user_timezone or "UTC",
                max_events=history_limit or 5,
            )
            print(f"[Fun Content] fetch_this_day_in_history returned {len(events)} events")
            content["this_day_in_history"] = events
        elif segment == "quote_of_the_day":
            content["quote_of_the_day"] = await fetch_quote_of_the_day()
        elif segment == "dad_joke":
            content["dad_joke"] = await fetch_dad_joke()
        elif segment == "word_of_the_day":
            content["word_of_the_day"] = await fetch_word_of_the_day(
                user_timezone=user_timezone,
            )
        elif segment == "sports_history":
            content["sports_history"] = await fetch_sports_history(user_timezone=user_timezone or "UTC")

    return content


def format_fun_content_for_agent(content: dict, user_timezone: str = None) -> str:
    """Format fun content for the Claude agent.

    Args:
        content: Dict with content for each segment type
        user_timezone: IANA timezone string for date formatting
    """
    lines = ["# Fun Segments\n"]

    # This day in history
    if "this_day_in_history" in content and content["this_day_in_history"]:
        lines.append("## This Day in History\n")
        today = get_user_now(user_timezone)
        lines.append(f"*{today.strftime('%B %d')}*\n")

        for event in content["this_day_in_history"]:
            emoji = "📅" if event.category == "event" else "🎂" if event.category == "birth" else "🕯️"
            lines.append(f"- **{event.year}** {emoji}: {event.description}")
        lines.append("")

    # Quote of the day
    if "quote_of_the_day" in content and content["quote_of_the_day"]:
        quote = content["quote_of_the_day"]
        lines.append("## Quote of the Day\n")
        lines.append(f'> "{quote.text}"')
        lines.append(f"*— {quote.author}*\n")

    # Word of the day
    if "word_of_the_day" in content and content["word_of_the_day"]:
        word = content["word_of_the_day"]
        lines.append("## Word of the Day\n")
        lines.append(f"**{word.word.title()}** ({word.part_of_speech})")
        if word.pronunciation:
            lines.append(f"*Pronunciation: {word.pronunciation}*")
        lines.append(f"\n{word.definition}")
        if word.example:
            lines.append(f'\n*Example: "{word.example}"*')
        lines.append("")

    # Dad joke
    if "dad_joke" in content and content["dad_joke"]:
        joke = content["dad_joke"]
        lines.append("## Dad Joke\n")
        if joke.punchline:
            lines.append(f"Q: {joke.setup}")
            lines.append(f"A: {joke.punchline}")
        else:
            lines.append(joke.setup)
        lines.append("")

    # Sports history
    if "sports_history" in content and content["sports_history"]:
        lines.append("## On This Day in Sports\n")
        for event in content["sports_history"]:
            lines.append(f"- **{event.year}**: {event.description}")
        lines.append("")

    return "\n".join(lines)
