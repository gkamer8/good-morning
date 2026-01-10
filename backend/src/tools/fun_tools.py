"""Fun segment tools - This Day in History, quotes, trivia, etc."""

import random
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx


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
    limit_events: int = 5,
    limit_births: int = 3,
    limit_deaths: int = 2,
    total_limit: Optional[int] = None,
    user_timezone: str = None,
) -> list[HistoricalEvent]:
    """Fetch events that happened on this day in history.

    Args:
        limit_events: Max selected historical events
        limit_births: Max notable births
        limit_deaths: Max notable deaths
        total_limit: If set, return only the top N most important events total
                     (events prioritized over births over deaths, then by recency)
        user_timezone: IANA timezone string for determining "today"
    """
    from src.utils.timezone import get_user_now

    now = get_user_now(user_timezone)
    # Wikipedia API requires zero-padded month and day
    month = f"{now.month:02d}"
    day = f"{now.day:02d}"

    events = []

    try:
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
        for item in selected[:limit_events]:
            events.append(
                HistoricalEvent(
                    year=item.get("year", 0),
                    description=item.get("text", ""),
                    category="event",
                )
            )

        # Notable births
        births = data.get("births", [])
        for item in births[:limit_births]:
            events.append(
                HistoricalEvent(
                    year=item.get("year", 0),
                    description=f"{item.get('text', '')} was born",
                    category="birth",
                )
            )

        # Notable deaths
        deaths = data.get("deaths", [])
        for item in deaths[:limit_deaths]:
            events.append(
                HistoricalEvent(
                    year=item.get("year", 0),
                    description=f"{item.get('text', '')} passed away",
                    category="death",
                )
            )

    except Exception as e:
        print(f"Error fetching historical events: {e}")

    print(f"[History] fetch_this_day_in_history: total_limit={total_limit!r}, fetched {len(events)} events before filtering")

    # If total_limit is set, return only the top N most important events
    # Priority: events > births > deaths, then by recency (more recent history first)
    if total_limit is not None and len(events) > total_limit:
        def importance_key(event: HistoricalEvent) -> tuple[int, int]:
            category_priority = {"event": 0, "birth": 1, "death": 2}
            return (category_priority.get(event.category, 3), -event.year)

        events.sort(key=importance_key)
        events = events[:total_limit]

    print(f"[History] Returning {len(events)} events after filtering")
    return events


async def fetch_quote_of_the_day() -> Optional[Quote]:
    """Fetch an inspirational quote."""
    # Using ZenQuotes API (free, no key required)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get("https://zenquotes.io/api/today")
            response.raise_for_status()
            data = response.json()

        if data and len(data) > 0:
            quote_data = data[0]
            return Quote(
                text=quote_data.get("q", ""),
                author=quote_data.get("a", "Unknown"),
            )

    except Exception as e:
        print(f"Error fetching quote: {e}")

    # Fallback quotes
    fallback_quotes = [
        Quote("The only way to do great work is to love what you do.", "Steve Jobs"),
        Quote("Innovation distinguishes between a leader and a follower.", "Steve Jobs"),
        Quote("Stay hungry, stay foolish.", "Steve Jobs"),
        Quote("The future belongs to those who believe in the beauty of their dreams.", "Eleanor Roosevelt"),
        Quote("It is during our darkest moments that we must focus to see the light.", "Aristotle"),
    ]
    return random.choice(fallback_quotes)


async def fetch_dad_joke() -> Optional[DadJoke]:
    """Fetch a random dad joke."""
    try:
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

    except Exception as e:
        print(f"Error fetching dad joke: {e}")

    # Fallback jokes
    fallback_jokes = [
        DadJoke("Why don't scientists trust atoms?", "Because they make up everything!"),
        DadJoke("I used to hate facial hair...", "But then it grew on me."),
        DadJoke("What do you call a fake noodle?", "An impasta!"),
        DadJoke("Why did the scarecrow win an award?", "Because he was outstanding in his field!"),
    ]
    return random.choice(fallback_jokes)


async def fetch_word_of_the_day(user_timezone: str = None) -> Optional[WordOfTheDay]:
    """Fetch word of the day.

    Args:
        user_timezone: IANA timezone string for determining the day of year
    """
    from src.utils.timezone import get_user_now

    # Using Free Dictionary API
    # Generate a random interesting word from a curated list
    interesting_words = [
        "serendipity", "ephemeral", "eloquent", "resilience", "ubiquitous",
        "quintessential", "juxtaposition", "paradigm", "ethereal", "mellifluous",
        "perspicacious", "surreptitious", "ineffable", "luminous", "enigmatic",
        "ephemeral", "cacophony", "epiphany", "labyrinthine", "vicissitude",
    ]

    # Pick based on day of year for consistency
    day_of_year = get_user_now(user_timezone).timetuple().tm_yday
    word = interesting_words[day_of_year % len(interesting_words)]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
            )
            response.raise_for_status()
            data = response.json()

        if data and len(data) > 0:
            entry = data[0]
            meanings = entry.get("meanings", [])

            if meanings:
                meaning = meanings[0]
                definitions = meaning.get("definitions", [])

                if definitions:
                    definition = definitions[0]

                    phonetic = ""
                    phonetics = entry.get("phonetics", [])
                    for p in phonetics:
                        if p.get("text"):
                            phonetic = p["text"]
                            break

                    return WordOfTheDay(
                        word=word,
                        part_of_speech=meaning.get("partOfSpeech", ""),
                        definition=definition.get("definition", ""),
                        example=definition.get("example"),
                        pronunciation=phonetic or None,
                    )

    except Exception as e:
        print(f"Error fetching word definition: {e}")

    return None


async def fetch_sports_history() -> list[HistoricalEvent]:
    """Fetch sports events that happened on this day."""
    # This would ideally use a sports history API
    # For now, we'll rely on the Wikipedia API and filter
    events = await fetch_this_day_in_history(limit_events=10, limit_births=0, limit_deaths=0)

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
                total_limit=history_limit,
                user_timezone=user_timezone,
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
            content["sports_history"] = await fetch_sports_history()

    return content


def format_fun_content_for_agent(content: dict, user_timezone: str = None) -> str:
    """Format fun content for the Claude agent.

    Args:
        content: Dict with content for each segment type
        user_timezone: IANA timezone string for date formatting
    """
    from src.utils.timezone import get_user_now

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
