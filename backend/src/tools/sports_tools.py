"""Sports data fetching tools - ESPN, TheSportsDB, and other free APIs."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import httpx


@dataclass
class GameScore:
    """A game score/result."""

    league: str
    home_team: str
    away_team: str
    home_score: Optional[int]
    away_score: Optional[int]
    status: str  # scheduled, in_progress, final, postponed
    start_time: Optional[datetime]
    venue: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None


@dataclass
class SportsNews:
    """Sports news/headline."""

    league: str
    headline: str
    description: str
    url: Optional[str] = None
    published: Optional[datetime] = None


# ESPN API endpoints (unofficial but widely used)
ESPN_API_BASE = "https://site.api.espn.com/apis/site/v2/sports"

LEAGUE_ENDPOINTS = {
    "nfl": f"{ESPN_API_BASE}/football/nfl",
    "mlb": f"{ESPN_API_BASE}/baseball/mlb",
    "nba": f"{ESPN_API_BASE}/basketball/nba",
    "nhl": f"{ESPN_API_BASE}/hockey/nhl",
    "mls": f"{ESPN_API_BASE}/soccer/usa.1",
    "premier_league": f"{ESPN_API_BASE}/soccer/eng.1",
    "ncaaf": f"{ESPN_API_BASE}/football/college-football",
    "ncaab": f"{ESPN_API_BASE}/basketball/mens-college-basketball",
    "pga": f"{ESPN_API_BASE}/golf/pga",
    "atp": f"{ESPN_API_BASE}/tennis/atp",
    "wta": f"{ESPN_API_BASE}/tennis/wta",
}


async def fetch_espn_scoreboard(league: str) -> list[GameScore]:
    """Fetch scoreboard from ESPN API."""
    if league not in LEAGUE_ENDPOINTS:
        return []

    endpoint = f"{LEAGUE_ENDPOINTS[league]}/scoreboard"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()

        games = []
        events = data.get("events", [])

        for event in events:
            competitions = event.get("competitions", [])
            if not competitions:
                continue

            competition = competitions[0]
            competitors = competition.get("competitors", [])

            if len(competitors) < 2:
                continue

            # ESPN uses home/away designation
            home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])

            # Get status
            status_data = competition.get("status", {})
            status_type = status_data.get("type", {}).get("name", "")

            if status_type == "STATUS_FINAL":
                status = "final"
            elif status_type == "STATUS_IN_PROGRESS":
                status = "in_progress"
            elif status_type == "STATUS_SCHEDULED":
                status = "scheduled"
            elif status_type == "STATUS_POSTPONED":
                status = "postponed"
            else:
                status = status_type.lower().replace("status_", "")

            # Parse start time
            start_time = None
            if event.get("date"):
                try:
                    start_time = datetime.fromisoformat(
                        event["date"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            # Get scores
            home_score = None
            away_score = None
            if status in ["final", "in_progress"]:
                home_score = int(home.get("score", 0))
                away_score = int(away.get("score", 0))

            # Get headline if available
            headline = event.get("name", "")
            summary = None
            if competition.get("headlines"):
                headline_data = competition["headlines"][0]
                headline = headline_data.get("shortLinkText", headline)
                summary = headline_data.get("description")

            games.append(
                GameScore(
                    league=league.upper(),
                    home_team=home.get("team", {}).get("displayName", "Unknown"),
                    away_team=away.get("team", {}).get("displayName", "Unknown"),
                    home_score=home_score,
                    away_score=away_score,
                    status=status,
                    start_time=start_time,
                    venue=competition.get("venue", {}).get("fullName"),
                    headline=headline,
                    summary=summary,
                )
            )

        return games

    except Exception as e:
        print(f"Error fetching ESPN scoreboard for {league}: {e}")
        return []


def filter_games_for_briefing(
    games: list[GameScore],
    user_timezone: str = "America/New_York",
    max_days_future: int = 5,
) -> list[GameScore]:
    """Filter out games too far in the future.

    Args:
        games: List of games from ESPN
        user_timezone: User's timezone string
        max_days_future: Maximum days ahead to include scheduled games

    Returns:
        Filtered list of games within the time window
    """
    if not games:
        return []

    try:
        tz = ZoneInfo(user_timezone)
    except Exception:
        tz = ZoneInfo("America/New_York")

    now_local = datetime.now(tz)
    today = now_local.date()
    yesterday = today - timedelta(days=1)
    max_future_date = today + timedelta(days=max_days_future)

    filtered = []
    for game in games:
        # Always include in-progress games
        if game.status == "in_progress":
            filtered.append(game)
            continue

        # Include finals from today or yesterday
        if game.status == "final":
            if game.start_time:
                game_date = game.start_time.astimezone(tz).date()
                if game_date >= yesterday:
                    filtered.append(game)
            continue

        # For scheduled games: filter by date range
        if game.status == "scheduled" and game.start_time:
            game_date = game.start_time.astimezone(tz).date()
            # Only include if within the next N days
            if today <= game_date <= max_future_date:
                filtered.append(game)
            continue

        # Postponed games: include if recent
        if game.status == "postponed" and game.start_time:
            game_date = game.start_time.astimezone(tz).date()
            if game_date >= yesterday and game_date <= max_future_date:
                filtered.append(game)

    return filtered


async def fetch_espn_news(league: str, limit: int = 5) -> list[SportsNews]:
    """Fetch news/headlines from ESPN API."""
    if league not in LEAGUE_ENDPOINTS:
        return []

    endpoint = f"{LEAGUE_ENDPOINTS[league]}/news"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(endpoint, params={"limit": limit})
            response.raise_for_status()
            data = response.json()

        news = []
        articles = data.get("articles", [])

        for article in articles[:limit]:
            published = None
            if article.get("published"):
                try:
                    published = datetime.fromisoformat(
                        article["published"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            news.append(
                SportsNews(
                    league=league.upper(),
                    headline=article.get("headline", ""),
                    description=article.get("description", ""),
                    url=article.get("links", {}).get("web", {}).get("href"),
                    published=published,
                )
            )

        return news

    except Exception as e:
        print(f"Error fetching ESPN news for {league}: {e}")
        return []


async def get_scores_for_leagues(
    leagues: list[str],
    user_timezone: str = "America/New_York",
) -> dict[str, list[GameScore]]:
    """Fetch scores for multiple leagues.

    Args:
        leagues: List of league identifiers
        user_timezone: User's timezone for filtering

    Returns:
        Dict mapping league name to list of filtered games
    """
    results = {}

    for league in leagues:
        league_key = league.lower()
        scores = await fetch_espn_scoreboard(league_key)
        filtered = filter_games_for_briefing(scores, user_timezone)
        results[league_key] = filtered

    return results


async def get_sports_news(
    leagues: list[str],
    limit_per_league: int = 3,
) -> list[SportsNews]:
    """Fetch news for multiple leagues."""
    all_news = []

    for league in leagues:
        league_key = league.lower()
        news = await fetch_espn_news(league_key, limit=limit_per_league)
        all_news.extend(news)

    # Sort by published date
    all_news.sort(
        key=lambda n: n.published or datetime.min,
        reverse=True,
    )

    return all_news


async def get_team_updates(
    teams: list[dict],
    user_timezone: str = "America/New_York",
) -> list[GameScore]:
    """Get recent game info for specific teams.

    Args:
        teams: List of dicts with 'name' and 'league' keys
        user_timezone: User's timezone for filtering
    """
    relevant_games = []
    leagues_to_check = set(t["league"].lower() for t in teams)
    team_names = set(t["name"].lower() for t in teams)

    # Fetch scoreboards for relevant leagues
    for league in leagues_to_check:
        scores = await fetch_espn_scoreboard(league)
        # Filter first, then check for team matches
        filtered_scores = filter_games_for_briefing(scores, user_timezone)

        for game in filtered_scores:
            home_lower = game.home_team.lower()
            away_lower = game.away_team.lower()

            # Check if any tracked team is playing
            if any(
                team_name in home_lower or team_name in away_lower
                for team_name in team_names
            ):
                relevant_games.append(game)

    return relevant_games


def format_sports_for_agent(
    scores: dict[str, list[GameScore]],
    news: list[SportsNews],
    team_games: list[GameScore],
    user_timezone: str = "America/New_York",
    favorite_teams: list[dict] = None,
) -> str:
    """Format sports data for the Claude agent."""
    try:
        tz = ZoneInfo(user_timezone)
    except Exception:
        tz = ZoneInfo("America/New_York")

    today = datetime.now(tz).date()
    lines = ["# Sports Update\n"]

    # Add context about favorite teams
    if favorite_teams:
        team_names = [t.get("name", "") for t in favorite_teams if t.get("name")]
        if team_names:
            lines.append(f"**User's favorite teams:** {', '.join(team_names)}\n")

    def format_game_time(game: GameScore) -> str:
        """Format game time with date context."""
        if not game.start_time:
            return "TBD"
        local_time = game.start_time.astimezone(tz)
        if local_time.date() == today:
            return f"Today at {local_time.strftime('%I:%M %p')}"
        else:
            return local_time.strftime("%b %d at %I:%M %p")

    # Featured team games first
    if team_games:
        lines.append("## Your Teams\n")
        for game in team_games:
            if game.status == "final":
                lines.append(
                    f"**{game.league}:** {game.away_team} {game.away_score} @ "
                    f"{game.home_team} {game.home_score} (Final)"
                )
                if game.summary:
                    lines.append(f"  *{game.summary}*")
            elif game.status == "in_progress":
                lines.append(
                    f"**{game.league}:** {game.away_team} {game.away_score} @ "
                    f"{game.home_team} {game.home_score} (In Progress)"
                )
            elif game.status == "scheduled":
                time_str = format_game_time(game)
                lines.append(
                    f"**{game.league}:** {game.away_team} @ {game.home_team} ({time_str})"
                )
            lines.append("")
        lines.append("---\n")

    # Scores by league
    for league, games in scores.items():
        if not games:
            continue

        lines.append(f"## {league.upper()} Scores\n")

        # Separate final games from upcoming
        final_games = [g for g in games if g.status == "final"]
        upcoming_games = [g for g in games if g.status != "final"]

        if final_games:
            lines.append("### Final")
            for game in final_games[:5]:  # Limit to 5
                lines.append(
                    f"- {game.away_team} **{game.away_score}** @ "
                    f"{game.home_team} **{game.home_score}**"
                )
            lines.append("")

        if upcoming_games:
            lines.append("### Upcoming/In Progress")
            for game in upcoming_games[:5]:
                if game.status == "in_progress":
                    lines.append(
                        f"- {game.away_team} {game.away_score} @ "
                        f"{game.home_team} {game.home_score} (LIVE)"
                    )
                else:
                    time_str = format_game_time(game)
                    lines.append(f"- {game.away_team} @ {game.home_team} ({time_str})")
            lines.append("")

        lines.append("---\n")

    # Sports news
    if news:
        lines.append("## Sports Headlines\n")
        for item in news[:10]:
            lines.append(f"**[{item.league}]** {item.headline}")
            if item.description:
                lines.append(f"  {item.description[:200]}...")
            lines.append("")

    return "\n".join(lines)
