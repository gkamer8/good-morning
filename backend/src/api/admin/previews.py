"""Admin content preview routes (RSS, API, Sports)."""

import re

import feedparser
import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.database import UserSettings, get_session
from src.tools.sports_tools import LEAGUE_ENDPOINTS, fetch_espn_scoreboard, get_team_updates

from .health import EXTERNAL_APIS_TO_CHECK, RSS_FEEDS_TO_CHECK


router = APIRouter()


@router.get("/rss-preview")
async def get_rss_preview(request: Request, feed: str):
    """Get preview of stories from an RSS feed."""
    from . import is_authenticated
    
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    feed_url = RSS_FEEDS_TO_CHECK.get(feed)
    if not feed_url:
        return JSONResponse({"error": f"Unknown feed: {feed}"}, status_code=404)

    try:
        headers = {"User-Agent": "MorningDrive/1.0 (Personal News Aggregator)"}
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            response = await client.get(feed_url, follow_redirects=True)
            response.raise_for_status()

        parsed = feedparser.parse(response.text)

        if parsed.bozo and not parsed.entries:
            return JSONResponse({"error": "Failed to parse RSS feed"}, status_code=500)

        stories = []
        for entry in parsed.entries[:5]:
            published = ""
            if hasattr(entry, "published"):
                published = entry.published
            elif hasattr(entry, "updated"):
                published = entry.updated

            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary
                summary = re.sub(r'<[^>]+>', '', summary)
                if len(summary) > 200:
                    summary = summary[:200] + "..."

            stories.append({
                "title": entry.get("title", "No title"),
                "link": entry.get("link", "#"),
                "published": published,
                "summary": summary,
            })

        return JSONResponse({
            "feed": feed,
            "url": feed_url,
            "stories": stories,
        })

    except httpx.TimeoutException:
        return JSONResponse({"error": "Request timed out"}, status_code=504)
    except httpx.HTTPStatusError as e:
        return JSONResponse({"error": f"HTTP error: {e.response.status_code}"}, status_code=502)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api-preview")
async def get_api_preview(request: Request, api: str):
    """Get preview of data from an external API."""
    from . import is_authenticated
    
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    api_config = EXTERNAL_APIS_TO_CHECK.get(api)
    if not api_config:
        return JSONResponse({"error": f"Unknown API: {api}"}, status_code=404)

    if isinstance(api_config, tuple):
        url, headers = api_config
    else:
        url = api_config
        headers = {}

    try:
        default_headers = {"User-Agent": "MorningDrive/1.0 Preview"}
        default_headers.update(headers)

        async with httpx.AsyncClient(timeout=10.0, headers=default_headers) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

        preview_data = {"api": api, "url": url}

        if "Wikipedia" in api:
            data = response.json()
            events = data.get("events", [])[:5]
            preview_data["type"] = "events"
            preview_data["items"] = [
                {"year": str(event.get("year", "")), "text": event.get("text", "")}
                for event in events
            ]

        elif "ZenQuotes" in api:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                quote = data[0]
                preview_data["type"] = "quote"
                preview_data["items"] = [{"quote": quote.get("q", ""), "author": quote.get("a", "Unknown")}]
            else:
                preview_data["type"] = "quote"
                preview_data["items"] = []

        elif "dadjoke" in api:
            data = response.json()
            preview_data["type"] = "joke"
            preview_data["items"] = [{"joke": data.get("joke", "No joke found")}]

        elif "Open-Meteo" in api or "Weather" in api:
            data = response.json()
            current = data.get("current_weather", {})
            preview_data["type"] = "weather"
            preview_data["items"] = [{
                "temperature": f"{current.get('temperature', 'N/A')}°C",
                "windspeed": f"{current.get('windspeed', 'N/A')} km/h",
                "weathercode": current.get("weathercode", "N/A"),
                "time": current.get("time", "N/A"),
            }]

        elif "ESPN" in api:
            data = response.json()
            events = data.get("events", [])[:5]
            preview_data["type"] = "sports"
            preview_data["items"] = []
            for event in events:
                name = event.get("name", "Unknown Game")
                status = event.get("status", {}).get("type", {}).get("shortDetail", "")
                competitions = event.get("competitions", [])
                score = ""
                if competitions:
                    competitors = competitions[0].get("competitors", [])
                    if len(competitors) >= 2:
                        scores = [f"{c.get('team', {}).get('abbreviation', '?')}: {c.get('score', '?')}" for c in competitors]
                        score = " vs ".join(scores)
                preview_data["items"].append({"name": name, "status": status, "score": score})

        elif "Yahoo Finance" in api:
            data = response.json()
            result = data.get("chart", {}).get("result", [])
            if result:
                meta = result[0].get("meta", {})
                price = meta.get("regularMarketPrice", 0)
                prev_close = meta.get("chartPreviousClose", 0)
                change = price - prev_close if prev_close else 0
                change_pct = (change / prev_close * 100) if prev_close else 0
                preview_data["type"] = "market"
                preview_data["items"] = [{
                    "symbol": meta.get("symbol", "^GSPC"),
                    "name": meta.get("shortName", "S&P 500"),
                    "price": f"${price:,.2f}",
                    "change": f"{change:+.2f} ({change_pct:+.2f}%)",
                    "high": f"${meta.get('regularMarketDayHigh', 0):,.2f}",
                    "low": f"${meta.get('regularMarketDayLow', 0):,.2f}",
                }]
            else:
                preview_data["type"] = "error"
                preview_data["items"] = [{"error": "No data returned"}]

        else:
            try:
                data = response.json()
                if isinstance(data, dict):
                    preview_data["type"] = "json"
                    preview_data["items"] = [{"raw": str(data)[:500]}]
                elif isinstance(data, list):
                    preview_data["type"] = "json"
                    preview_data["items"] = [{"raw": str(data[:3])[:500]}]
                else:
                    preview_data["type"] = "text"
                    preview_data["items"] = [{"raw": str(data)[:500]}]
            except Exception:
                preview_data["type"] = "text"
                preview_data["items"] = [{"raw": response.text[:500]}]

        return JSONResponse(preview_data)

    except httpx.TimeoutException:
        return JSONResponse({"error": "Request timed out"}, status_code=504)
    except httpx.HTTPStatusError as e:
        return JSONResponse({"error": f"HTTP error: {e.response.status_code}"}, status_code=502)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/sports-preview")
async def get_sports_preview(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Preview sports data based on user settings."""
    from . import is_authenticated
    
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await session.execute(select(UserSettings).limit(1))
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        return JSONResponse({"error": "No user settings found"}, status_code=404)

    sports_leagues = user_settings.sports_leagues or []
    sports_teams = user_settings.sports_teams or []

    if not sports_leagues and not sports_teams:
        return JSONResponse({
            "leagues": [],
            "teams": [],
            "message": "No sports leagues or teams configured in settings",
        })

    preview_data = {
        "configured_leagues": sports_leagues,
        "configured_teams": sports_teams,
        "leagues": [],
        "team_games": [],
    }

    for league in sports_leagues:
        league_key = league.lower()
        if league_key not in LEAGUE_ENDPOINTS:
            preview_data["leagues"].append({
                "league": league,
                "error": f"Unknown league: {league}",
                "games": [],
            })
            continue

        try:
            games = await fetch_espn_scoreboard(league_key, "America/New_York")
            preview_data["leagues"].append({
                "league": league.upper(),
                "endpoint": f"{LEAGUE_ENDPOINTS[league_key]}/scoreboard",
                "games": [
                    {
                        "home_team": g.home_team,
                        "away_team": g.away_team,
                        "home_score": g.home_score,
                        "away_score": g.away_score,
                        "status": g.status,
                        "start_time": g.start_time.isoformat() if g.start_time else None,
                    }
                    for g in games[:5]
                ],
                "total_games": len(games),
            })
        except Exception as e:
            preview_data["leagues"].append({
                "league": league.upper(),
                "error": str(e),
                "games": [],
            })

    if sports_teams:
        try:
            team_games = await get_team_updates(sports_teams)
            preview_data["team_games"] = [
                {
                    "league": g.league,
                    "home_team": g.home_team,
                    "away_team": g.away_team,
                    "home_score": g.home_score,
                    "away_score": g.away_score,
                    "status": g.status,
                    "headline": g.headline,
                }
                for g in team_games
            ]
        except Exception as e:
            preview_data["team_games_error"] = str(e)

    return JSONResponse(preview_data)

