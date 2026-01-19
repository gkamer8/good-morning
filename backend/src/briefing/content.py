"""Content gathering functions for briefing generation."""

import asyncio

from src.api.schemas import LengthMode
from src.briefing.generation_errors import catch_async_generation_errors
from src.briefing.length_rules import LENGTH_RULES
from src.storage.database import UserSettings
from src.tools.finance_tools import format_market_for_agent, get_market_summary
from src.tools.fun_tools import format_fun_content_for_agent, get_fun_content
from src.tools.music_tools import format_music_for_agent, get_music_piece_for_date
from src.tools.news_tools import format_news_for_agent, get_top_news
from src.tools.sports_tools import (
    format_sports_for_agent,
    get_scores_for_leagues,
    get_sports_news,
    get_team_updates,
)
from src.tools.weather_tools import format_weather_for_agent, get_weather_for_locations
from src.utils.timezone import get_user_now


@catch_async_generation_errors(
    fallback_fn=None  # Not recoverable
)
async def gather_all_content(
    _briefing_id: int,
    settings: UserSettings,
    include_music: bool = False,
    length_mode: LengthMode = LengthMode.SHORT,
    user_timezone: str = None,
) -> dict:
    """Gather content from all sources in parallel.

    Args:
        settings: User settings
        include_music: Whether to include music segment
        length_mode: LengthMode.SHORT or LengthMode.LONG - controls content limits
        user_timezone: IANA timezone string for date/time operations
    """
    rules = LENGTH_RULES[length_mode]
    print(f"[Content] gather_all_content: length_mode={length_mode!r}, rules.history_events={rules.history_events}")

    async def fetch_news():
        result = await get_top_news(
            sources=settings.news_sources or ["bbc", "npr", "nyt"],
            topics=settings.news_topics or ["top", "technology", "business"],
            limit=10,
            stories_per_source=rules.news_stories_per_source,
        )
        return {
            "text": format_news_for_agent(result.articles),
            "errors": result.errors,
        }

    async def fetch_sports():
        leagues = settings.sports_leagues or ["nfl", "mlb", "nhl"]
        teams = settings.sports_teams or []

        scores = await get_scores_for_leagues(
            leagues,
            user_timezone=user_timezone,
            favorite_teams_only=rules.sports_favorite_teams_only,
            favorite_teams=teams,
        )
        news = await get_sports_news(leagues, limit_per_league=2)
        team_games = await get_team_updates(teams, user_timezone=user_timezone) if teams else []

        return format_sports_for_agent(
            scores, news, team_games, user_timezone=user_timezone, favorite_teams=teams
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
            history_limit=rules.history_events,
            user_timezone=user_timezone,
        )
        return format_fun_content_for_agent(content, user_timezone=user_timezone)

    async def fetch_market():
        if "market_minute" in (settings.fun_segments or []):
            summary = await get_market_summary(
                movers_limit=rules.finance_movers_limit,
                user_timezone=user_timezone,
            )
            return format_market_for_agent(summary, user_timezone=user_timezone)
        return ""

    async def fetch_music():
        """Fetch music piece info (audio download is handled by orchestrator)."""
        if include_music:
            today = get_user_now(user_timezone).strftime("%Y-%m-%d")
            piece = await get_music_piece_for_date(today)

            if piece:
                return {
                    "text": format_music_for_agent(piece),
                    "piece": piece,
                }
            else:
                print("WARNING: No music pieces available in database")
                return {"text": "", "piece": None}
        return {"text": "", "piece": None}

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
    news_result = results[0] if not isinstance(results[0], Exception) else {"text": "News unavailable.", "errors": []}
    music_result = results[5] if not isinstance(results[5], Exception) else {"text": "", "piece": None}

    content = {
        "news": news_result.get("text", "News unavailable.") if isinstance(news_result, dict) else "News unavailable.",
        "news_errors": news_result.get("errors", []) if isinstance(news_result, dict) else [],
        "sports": results[1] if not isinstance(results[1], Exception) else "Sports unavailable.",
        "weather": results[2] if not isinstance(results[2], Exception) else "Weather unavailable.",
        "fun": results[3] if not isinstance(results[3], Exception) else "",
        "market": results[4] if not isinstance(results[4], Exception) else "",
        "music": music_result.get("text", "") if isinstance(music_result, dict) else "",
        "music_piece": music_result.get("piece") if isinstance(music_result, dict) else None,
    }

    return content

