"""Admin interface routes for Morning Drive."""

import asyncio
import io
import socket
import time
from datetime import datetime
from typing import Optional

import anthropic
import feedparser
import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from pydub import AudioSegment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.template_config import templates
from src.config import get_settings
from src.api.schemas import SettingsResponse
from src.storage.database import AdminSettings, Briefing, InviteCode, MusicPiece, Schedule, User, UserSettings, get_session
from src.storage.minio_storage import get_minio_storage


# === Health Check Configuration ===

# RSS Feeds to check (one per source to avoid too many requests)
RSS_FEEDS_TO_CHECK = {
    "BBC News": "http://feeds.bbci.co.uk/news/rss.xml",
    "NPR": "https://feeds.npr.org/1001/rss.xml",
    "New York Times": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Hacker News": "https://hnrss.org/frontpage",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
}

# External APIs to check
EXTERNAL_APIS_TO_CHECK = {
    "Wikipedia (This Day in History)": "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/1/1",
    "ZenQuotes (Quote of the Day)": "https://zenquotes.io/api/today",
    "icanhazdadjoke (Dad Jokes)": ("https://icanhazdadjoke.com/", {"Accept": "application/json"}),
    "Open-Meteo (Weather)": "https://api.open-meteo.com/v1/forecast?latitude=40.7&longitude=-74&current_weather=true",
    "Yahoo Finance (Market Data)": "https://query2.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1d&range=1d",
    "ESPN (Sports)": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
}


async def check_url_health(name: str, url: str, headers: dict = None, timeout: float = 10.0) -> dict:
    """Check if a URL is accessible and responding."""
    start_time = time.time()
    try:
        default_headers = {"User-Agent": "MorningDrive/1.0 HealthCheck"}
        if headers:
            default_headers.update(headers)
        async with httpx.AsyncClient(timeout=timeout, headers=default_headers) as client:
            response = await client.get(url, follow_redirects=True)
            elapsed = time.time() - start_time
            return {
                "name": name,
                "url": url,
                "status": "ok" if response.status_code < 400 else "error",
                "status_code": response.status_code,
                "response_time_ms": int(elapsed * 1000),
                "error": None if response.status_code < 400 else f"HTTP {response.status_code}",
            }
    except httpx.TimeoutException:
        elapsed = time.time() - start_time
        return {
            "name": name,
            "url": url,
            "status": "timeout",
            "status_code": None,
            "response_time_ms": int(elapsed * 1000),
            "error": "Request timed out",
        }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "name": name,
            "url": url,
            "status": "error",
            "status_code": None,
            "response_time_ms": int(elapsed * 1000),
            "error": str(e)[:100],
        }


async def check_minio_health() -> dict:
    """Check MinIO storage connectivity."""
    start_time = time.time()
    try:
        storage = get_minio_storage()
        await storage.ensure_bucket_exists()
        # Try to list objects (lightweight operation)
        await storage.list_files(prefix="")
        elapsed = time.time() - start_time
        return {
            "name": "MinIO Storage",
            "status": "ok",
            "response_time_ms": int(elapsed * 1000),
            "error": None,
        }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "name": "MinIO Storage",
            "status": "error",
            "response_time_ms": int(elapsed * 1000),
            "error": str(e)[:100],
        }


async def check_anthropic_health() -> dict:
    """Check Anthropic API key validity (without making a real request)."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        return {
            "name": "Anthropic API",
            "status": "not_configured",
            "response_time_ms": 0,
            "error": "API key not configured",
        }
    # Just verify the key format (actual test would cost money)
    return {
        "name": "Anthropic API",
        "status": "configured",
        "response_time_ms": 0,
        "error": None,
    }


async def check_elevenlabs_health() -> dict:
    """Check ElevenLabs API connectivity."""
    settings = get_settings()
    if not settings.elevenlabs_api_key:
        return {
            "name": "ElevenLabs API",
            "status": "not_configured",
            "response_time_ms": 0,
            "error": "API key not configured",
        }
    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": settings.elevenlabs_api_key}
            )
            elapsed = time.time() - start_time
            if response.status_code == 200:
                return {
                    "name": "ElevenLabs API",
                    "status": "ok",
                    "response_time_ms": int(elapsed * 1000),
                    "error": None,
                }
            elif response.status_code == 401:
                return {
                    "name": "ElevenLabs API",
                    "status": "error",
                    "response_time_ms": int(elapsed * 1000),
                    "error": "Invalid API key",
                }
            else:
                return {
                    "name": "ElevenLabs API",
                    "status": "error",
                    "response_time_ms": int(elapsed * 1000),
                    "error": f"HTTP {response.status_code}",
                }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "name": "ElevenLabs API",
            "status": "error",
            "response_time_ms": int(elapsed * 1000),
            "error": str(e)[:100],
        }


def get_audio_duration(audio_bytes: bytes) -> float:
    """Extract duration in seconds from audio file bytes."""
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
    return len(audio) / 1000.0  # pydub returns milliseconds


async def generate_music_description(title: str, composer: str) -> str:
    """Generate an interesting description for a classical music piece using Claude."""
    from src.prompts import render_prompt

    settings = get_settings()

    if not settings.anthropic_api_key:
        return ""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Render prompt from Jinja template
    prompt = render_prompt(
        "music_description.jinja2",
        title=title,
        composer=composer,
    )

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"Failed to generate music description: {e}")
        return ""


def get_server_url() -> str | None:
    """Get the server's URL that clients can connect to.

    Returns None in production (when accessed via public URL).
    Returns the local LAN IP for development.
    """
    import os

    # Check for explicit IP override
    if os.environ.get("SERVER_IP"):
        return f"http://{os.environ['SERVER_IP']}:{settings.port}"

    # Detect LAN IP via socket connection to external address
    # This gets the IP of the interface used to reach the internet
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()

        # Skip Docker internal IPs (192.168.65.x, 172.17.x.x, etc.)
        if ip.startswith("192.168.65.") or ip.startswith("172.17.") or ip.startswith("172.18."):
            return None  # Running in Docker - can't auto-detect host IP

        return f"http://{ip}:{settings.port}"
    except Exception:
        return None

router = APIRouter()
settings = get_settings()


def verify_admin_password(password: str) -> bool:
    """Verify the admin password."""
    return password == settings.admin_password


# Simple session storage (in production, use proper session management)
_admin_sessions: set[str] = set()


def generate_session_token() -> str:
    """Generate a simple session token."""
    import secrets
    return secrets.token_urlsafe(32)


def get_session_token(request: Request) -> Optional[str]:
    """Get session token from cookie."""
    return request.cookies.get("admin_session")


def is_authenticated(request: Request) -> bool:
    """Check if the request is authenticated."""
    token = get_session_token(request)
    return token is not None and token in _admin_sessions


# === Admin Pages ===


@router.get("/")
async def admin_index(request: Request):
    """Admin index - redirect to login or music page."""
    if is_authenticated(request):
        return RedirectResponse(url="/admin/music", status_code=302)
    return RedirectResponse(url="/admin/login", status_code=302)


@router.get("/login")
async def admin_login_page(request: Request, error: str = None):
    """Admin login page."""
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {"error": error, "is_authenticated": False},
    )


@router.post("/login")
async def admin_login(password: str = Form(...)):
    """Handle admin login."""
    if verify_admin_password(password):
        token = generate_session_token()
        _admin_sessions.add(token)
        response = RedirectResponse(url="/admin/music", status_code=302)
        response.set_cookie(
            key="admin_session",
            value=token,
            httponly=True,
            max_age=86400,  # 24 hours
            samesite="lax"
        )
        return response
    return RedirectResponse(url="/admin/login?error=Invalid+password", status_code=302)


@router.get("/logout")
async def admin_logout(request: Request):
    """Handle admin logout."""
    token = get_session_token(request)
    if token and token in _admin_sessions:
        _admin_sessions.discard(token)
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie("admin_session")
    return response


@router.get("/music")
async def admin_music_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    success: str = None,
    error: str = None,
):
    """Admin music management page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    # Get all music pieces
    result = await session.execute(
        select(MusicPiece).order_by(MusicPiece.composer, MusicPiece.title)
    )
    pieces = result.scalars().all()

    # Get server URL for app connection
    server_url = get_server_url()

    return templates.TemplateResponse(
        request,
        "admin/music.html",
        {
            "active_page": "admin-music",
            "is_authenticated": True,
            "pieces": pieces,
            "server_url": server_url,
            "success": success,
            "error": error,
        },
    )


@router.post("/music/upload")
async def admin_upload_music(
    request: Request,
    title: str = Form(...),
    composer: str = Form(...),
    file: UploadFile = None,
    session: AsyncSession = Depends(get_session),
):
    """Handle music upload from admin interface."""
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    if not file:
        return RedirectResponse(url="/admin/music?error=No+file+provided", status_code=302)

    # Validate file type
    if not file.content_type or not file.content_type.startswith("audio/"):
        return RedirectResponse(url="/admin/music?error=File+must+be+an+audio+file", status_code=302)

    # Generate S3 key
    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title).strip()
    safe_composer = "".join(c if c.isalnum() or c in " -_" else "" for c in composer).strip()
    s3_key = f"music/{safe_composer}/{safe_title}.mp3".replace(" ", "_").lower()

    # Read file content
    content = await file.read()
    if len(content) < 10000:
        return RedirectResponse(url="/admin/music?error=File+too+small+to+be+valid+audio", status_code=302)

    try:
        # Auto-detect duration from audio file (run in thread pool to avoid blocking)
        try:
            duration_seconds = await asyncio.to_thread(get_audio_duration, content)
        except Exception as e:
            print(f"Failed to detect audio duration: {e}")
            return RedirectResponse(
                url="/admin/music?error=Could+not+read+audio+file.+Make+sure+it's+a+valid+MP3.",
                status_code=302
            )

        # Auto-generate description using Claude
        description = await generate_music_description(title, composer)

        # Upload to MinIO
        storage = get_minio_storage()
        await storage.ensure_bucket_exists()
        result = await storage.upload_bytes(content, s3_key, content_type=file.content_type or "audio/mpeg")

        # Create database record
        piece = MusicPiece(
            title=title,
            composer=composer,
            description=description,
            s3_key=s3_key,
            duration_seconds=duration_seconds,
            file_size_bytes=result["size_bytes"],
            day_of_year_start=1,
            day_of_year_end=366,
            is_active=True,
        )
        session.add(piece)
        await session.commit()

        return RedirectResponse(
            url=f"/admin/music?success=Uploaded+{title}+successfully+(duration:+{int(duration_seconds)}s)",
            status_code=302
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/music?error=Upload+failed:+{str(e)[:50]}",
            status_code=302
        )


@router.post("/music/{piece_id}/delete")
async def admin_delete_music(
    request: Request,
    piece_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a music piece from admin interface."""
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    result = await session.execute(select(MusicPiece).where(MusicPiece.id == piece_id))
    piece = result.scalar_one_or_none()

    if not piece:
        return RedirectResponse(url="/admin/music?error=Music+piece+not+found", status_code=302)

    title = piece.title

    try:
        # Delete from MinIO
        storage = get_minio_storage()
        await storage.delete_file(piece.s3_key)

        # Delete from database
        await session.delete(piece)
        await session.commit()

        return RedirectResponse(
            url=f"/admin/music?success=Deleted+{title}",
            status_code=302
        )
    except Exception as e:
        return RedirectResponse(
            url=f"/admin/music?error=Delete+failed:+{str(e)[:50]}",
            status_code=302
        )


@router.get("/health")
async def admin_health_page(request: Request):
    """Admin health check page - shows status of all external dependencies."""
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    # Run all health checks in parallel
    rss_checks = []
    for name, url in RSS_FEEDS_TO_CHECK.items():
        rss_checks.append(check_url_health(name, url))

    api_checks = []
    for name, config in EXTERNAL_APIS_TO_CHECK.items():
        if isinstance(config, tuple):
            url, headers = config
            api_checks.append(check_url_health(name, url, headers))
        else:
            api_checks.append(check_url_health(name, config))

    # Run internal service checks
    internal_checks = [
        check_minio_health(),
        check_anthropic_health(),
        check_elevenlabs_health(),
    ]

    # Execute all checks concurrently
    all_results = await asyncio.gather(
        *rss_checks,
        *api_checks,
        *internal_checks,
        return_exceptions=True
    )

    # Split results back into categories
    rss_results = all_results[:len(rss_checks)]
    api_results = all_results[len(rss_checks):len(rss_checks) + len(api_checks)]
    internal_results = all_results[len(rss_checks) + len(api_checks):]

    # Convert exceptions to error dicts for template
    def normalize_result(result):
        if isinstance(result, Exception):
            return {
                "name": "Unknown",
                "status": "error",
                "response_time_ms": 0,
                "error": str(result)[:100],
            }
        return result

    rss_results = [normalize_result(r) for r in rss_results]
    api_results = [normalize_result(r) for r in api_results]
    internal_results = [normalize_result(r) for r in internal_results]

    # Calculate overall status
    all_statuses = [r.get("status", "error") for r in rss_results + api_results + internal_results]
    ok_count = sum(1 for s in all_statuses if s in ("ok", "configured"))
    warning_count = sum(1 for s in all_statuses if s in ("not_configured", "timeout"))
    error_count = sum(1 for s in all_statuses if s == "error")
    total = len(all_statuses)

    if error_count > 0:
        overall_status = "error"
        overall_text = f"{error_count} service(s) have errors"
    elif warning_count > 0:
        overall_status = "warning"
        overall_text = f"{warning_count} service(s) need attention"
    else:
        overall_status = "ok"
        overall_text = "All systems operational"

    return templates.TemplateResponse(
        request,
        "admin/health.html",
        {
            "active_page": "admin-health",
            "is_authenticated": True,
            "rss_results": rss_results,
            "api_results": api_results,
            "internal_results": internal_results,
            "overall_status": overall_status,
            "overall_text": overall_text,
            "ok_count": ok_count,
            "total_count": total,
            "last_checked": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
    )


@router.get("/rss-preview")
async def get_rss_preview(request: Request, feed: str):
    """Get preview of stories from an RSS feed."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    # Find the feed URL
    feed_url = RSS_FEEDS_TO_CHECK.get(feed)
    if not feed_url:
        return JSONResponse({"error": f"Unknown feed: {feed}"}, status_code=404)

    try:
        # Fetch and parse the RSS feed
        headers = {"User-Agent": "MorningDrive/1.0 (Personal News Aggregator)"}
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            response = await client.get(feed_url, follow_redirects=True)
            response.raise_for_status()

        # Parse the feed
        parsed = feedparser.parse(response.text)

        if parsed.bozo and not parsed.entries:
            return JSONResponse({"error": "Failed to parse RSS feed"}, status_code=500)

        # Extract the first 5 stories
        stories = []
        for entry in parsed.entries[:5]:
            # Get published date
            published = ""
            if hasattr(entry, "published"):
                published = entry.published
            elif hasattr(entry, "updated"):
                published = entry.updated

            # Get summary (truncate if too long)
            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary
                # Strip HTML tags for cleaner display
                import re
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
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    # Find the API config
    api_config = EXTERNAL_APIS_TO_CHECK.get(api)
    if not api_config:
        return JSONResponse({"error": f"Unknown API: {api}"}, status_code=404)

    # Extract URL and headers
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

        # Parse response based on API type
        preview_data = {"api": api, "url": url}

        if "Wikipedia" in api:
            # This Day in History - returns events for a specific date
            data = response.json()
            events = data.get("events", [])[:5]
            preview_data["type"] = "events"
            preview_data["items"] = [
                {
                    "year": str(event.get("year", "")),
                    "text": event.get("text", ""),
                }
                for event in events
            ]

        elif "ZenQuotes" in api:
            # Quote of the Day
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                quote = data[0]
                preview_data["type"] = "quote"
                preview_data["items"] = [{
                    "quote": quote.get("q", ""),
                    "author": quote.get("a", "Unknown"),
                }]
            else:
                preview_data["type"] = "quote"
                preview_data["items"] = []

        elif "dadjoke" in api:
            # Dad Joke
            data = response.json()
            preview_data["type"] = "joke"
            preview_data["items"] = [{
                "joke": data.get("joke", "No joke found"),
            }]

        elif "Open-Meteo" in api or "Weather" in api:
            # Weather data
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
            # Sports scoreboard
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
                preview_data["items"].append({
                    "name": name,
                    "status": status,
                    "score": score,
                })

        elif "Yahoo Finance" in api:
            # Yahoo Finance Chart API - extract market data
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
            # Generic JSON preview - show first few keys/values
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
    """Preview sports data based on user settings - shows what would be fetched for a briefing."""
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    # Get user settings
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

    # Import sports tools
    from src.tools.sports_tools import (
        LEAGUE_ENDPOINTS,
        fetch_espn_scoreboard,
        get_team_updates,
    )

    preview_data = {
        "configured_leagues": sports_leagues,
        "configured_teams": sports_teams,
        "leagues": [],
        "team_games": [],
    }

    # Fetch scoreboard data for each configured league
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
                    for g in games[:5]  # Limit to 5 games per league
                ],
                "total_games": len(games),
            })
        except Exception as e:
            preview_data["leagues"].append({
                "league": league.upper(),
                "error": str(e),
                "games": [],
            })

    # Fetch games for specific teams
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


@router.get("/scheduler")
async def admin_scheduler_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Admin scheduler monitoring page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    # Get scheduler instance
    from src.main import get_scheduler
    scheduler = get_scheduler()

    # Get all schedules with user info
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    schedules_result = await session.execute(
        select(Schedule, User)
        .outerjoin(User, Schedule.user_id == User.id)
        .order_by(Schedule.user_id)
    )
    schedules_data = []
    for schedule, user in schedules_result.all():
        schedules_data.append({
            "user_id": schedule.user_id,
            "user_name": user.display_name if user else None,
            "user_email": user.email if user else None,
            "enabled": schedule.enabled,
            "time": f"{schedule.time_hour:02d}:{schedule.time_minute:02d}",
            "days": ", ".join(day_names[d] for d in sorted(schedule.days_of_week)),
            "timezone": schedule.timezone,
        })

    # Get scheduler jobs
    jobs = []
    next_run = None
    scheduler_running = scheduler is not None and scheduler.running

    if scheduler_running:
        for job in scheduler.get_jobs():
            job_next_run = job.next_run_time
            if job_next_run:
                next_run_str = job_next_run.strftime("%Y-%m-%d %H:%M:%S %Z")
                if next_run is None:
                    next_run = next_run_str
            else:
                next_run_str = "Not scheduled"

            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run_str,
                "trigger": str(job.trigger),
            })

    # Get recent briefings with user info
    result = await session.execute(
        select(Briefing, User)
        .outerjoin(User, Briefing.user_id == User.id)
        .order_by(Briefing.created_at.desc())
        .limit(20)
    )
    briefings_raw = result.all()

    briefings = []
    for b, user in briefings_raw:
        errors = b.generation_errors if b.generation_errors else []
        rendered = b.rendered_prompts if b.rendered_prompts else {}
        segments_meta = b.segments_metadata if b.segments_metadata else {}

        # Include music_error from segments_metadata if present
        music_error = segments_meta.get("music_error")
        if music_error:
            errors = errors + [{
                "error_type": "Music Error",
                "segment": "music",
                "message": music_error,
                "timestamp": b.created_at.strftime("%Y-%m-%d %H:%M"),
            }]

        briefings.append({
            "id": b.id,
            "title": b.title,
            "created_at": b.created_at.strftime("%Y-%m-%d %H:%M"),
            "status": b.status,
            "duration": f"{int(b.duration_seconds // 60)}:{int(b.duration_seconds % 60):02d}" if b.duration_seconds else "-",
            "error_count": len(errors),
            "errors": errors,
            "has_prompts": bool(rendered),
            "rendered_prompts": rendered,
            "user_id": b.user_id,
            "user_name": user.display_name if user else None,
            "user_email": user.email if user else None,
        })

    return templates.TemplateResponse(
        request,
        "admin/scheduler.html",
        {
            "active_page": "admin-scheduler",
            "is_authenticated": True,
            "scheduler_running": scheduler_running,
            "schedules": schedules_data,
            "next_run": next_run,
            "jobs": jobs,
            "briefings": briefings,
            "last_checked": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
    )


# === Invite Code Management ===


@router.get("/invites")
async def admin_invites_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    success: str = None,
    error: str = None,
):
    """Admin invite code management page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    # Get all invite codes
    result = await session.execute(
        select(InviteCode).order_by(InviteCode.created_at.desc())
    )
    invites = result.scalars().all()

    # Enrich with user info for used codes
    invites_data = []
    for invite in invites:
        user_email = None
        if invite.used_by_user_id:
            user_result = await session.execute(
                select(User).where(User.id == invite.used_by_user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                user_email = user.email or user.display_name or f"User #{user.id}"

        invites_data.append({
            "id": invite.id,
            "code": invite.code,
            "created_at": invite.created_at.strftime("%Y-%m-%d %H:%M"),
            "max_uses": invite.max_uses,
            "use_count": invite.use_count,
            "expires_at": invite.expires_at.strftime("%Y-%m-%d %H:%M") if invite.expires_at else None,
            "note": invite.note,
            "used_by": user_email,
            "is_valid": invite.use_count < invite.max_uses and (
                invite.expires_at is None or invite.expires_at > datetime.now()
            ),
        })

    # Get invite test mode setting
    test_mode_result = await session.execute(
        select(AdminSettings).where(AdminSettings.key == "invite_test_mode_email")
    )
    test_mode_setting = test_mode_result.scalar_one_or_none()
    invite_test_mode_enabled = test_mode_setting is not None and test_mode_setting.value
    invite_test_mode_email = test_mode_setting.value if test_mode_setting else "gkamer@outlook.com"

    return templates.TemplateResponse(
        request,
        "admin/invites.html",
        {
            "active_page": "admin-invites",
            "is_authenticated": True,
            "invites": invites_data,
            "success": success,
            "error": error,
            "invite_test_mode_enabled": invite_test_mode_enabled,
            "invite_test_mode_email": invite_test_mode_email,
        },
    )


@router.post("/invites/create")
async def admin_create_invite(
    request: Request,
    note: str = Form(default=""),
    max_uses: int = Form(default=1),
    expires_days: int = Form(default=0),
    session: AsyncSession = Depends(get_session),
):
    """Create a new invite code."""
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    import secrets
    from datetime import timedelta, timezone

    # Generate unique code (uppercase, 8 chars)
    code = secrets.token_urlsafe(6).upper()[:8]

    # Calculate expiration if specified
    expires_at = None
    if expires_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

    invite = InviteCode(
        code=code,
        max_uses=max_uses,
        expires_at=expires_at,
        note=note or None,
    )
    session.add(invite)
    await session.commit()

    return RedirectResponse(
        url=f"/admin/invites?success=Created+invite+code:+{code}",
        status_code=302,
    )


@router.post("/invites/{invite_id}/delete")
async def admin_delete_invite(
    request: Request,
    invite_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete an invite code."""
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    result = await session.execute(
        select(InviteCode).where(InviteCode.id == invite_id)
    )
    invite = result.scalar_one_or_none()

    if not invite:
        return RedirectResponse(
            url="/admin/invites?error=Invite+code+not+found",
            status_code=302,
        )

    code = invite.code
    await session.delete(invite)
    await session.commit()

    return RedirectResponse(
        url=f"/admin/invites?success=Deleted+invite+code:+{code}",
        status_code=302,
    )


@router.post("/invites/test-mode/enable")
async def admin_enable_invite_test_mode(
    request: Request,
    email: str = Form(default="gkamer@outlook.com"),
    session: AsyncSession = Depends(get_session),
):
    """Enable invite test mode for a specific email."""
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    # Check if setting exists
    result = await session.execute(
        select(AdminSettings).where(AdminSettings.key == "invite_test_mode_email")
    )
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = email
    else:
        setting = AdminSettings(key="invite_test_mode_email", value=email)
        session.add(setting)

    await session.commit()

    return RedirectResponse(
        url=f"/admin/invites?success=Invite+test+mode+enabled+for+{email}",
        status_code=302,
    )


@router.post("/invites/test-mode/disable")
async def admin_disable_invite_test_mode(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Disable invite test mode."""
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    result = await session.execute(
        select(AdminSettings).where(AdminSettings.key == "invite_test_mode_email")
    )
    setting = result.scalar_one_or_none()

    if setting:
        await session.delete(setting)
        await session.commit()

    return RedirectResponse(
        url="/admin/invites?success=Invite+test+mode+disabled",
        status_code=302,
    )


# === User Management ===


@router.get("/users")
async def admin_users_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Admin user management page."""
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    # Get all users with their settings and schedules
    result = await session.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    users_data = []
    for user in users:
        # Get user's settings
        settings_result = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        user_settings = settings_result.scalar_one_or_none()

        # Get user's schedule
        schedule_result = await session.execute(
            select(Schedule).where(Schedule.user_id == user.id)
        )
        user_schedule = schedule_result.scalar_one_or_none()

        # Count user's briefings
        briefings_result = await session.execute(
            select(Briefing).where(Briefing.user_id == user.id)
        )
        briefings_count = len(briefings_result.scalars().all())

        # Convert schedule to dict
        schedule_dict = {}
        if user_schedule:
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            schedule_dict = {
                "enabled": user_schedule.enabled,
                "time": f"{user_schedule.time_hour:02d}:{user_schedule.time_minute:02d}",
                "days": ", ".join(day_names[d] for d in sorted(user_schedule.days_of_week)),
                "timezone": user_schedule.timezone,
            }

        users_data.append({
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "created_at": user.created_at.strftime("%Y-%m-%d %H:%M"),
            "last_login_at": user.last_login_at.strftime("%Y-%m-%d %H:%M") if user.last_login_at else None,
            "is_active": user.is_active,
            "has_settings": user_settings is not None,
            "schedule": schedule_dict,
            "briefings_count": briefings_count,
        })

    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "active_page": "admin-users",
            "is_authenticated": True,
            "users": users_data,
        },
    )


@router.get("/api/users/{user_id}/settings")
async def admin_get_user_settings(
    request: Request,
    user_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Get settings for a specific user (admin API).

    NOTE: This endpoint returns the same structure as SettingsResponse from the main API.
    If you add/remove fields from SettingsResponse, update this endpoint accordingly.
    The admin users page template depends on this structure for the "View Settings" modal.
    """
    if not is_authenticated(request):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        return JSONResponse({"error": "Settings not found"}, status_code=404)

    # Use the same serialization as the main settings API
    response = SettingsResponse(
        news_topics=user_settings.news_topics,
        news_sources=user_settings.news_sources,
        sports_teams=user_settings.sports_teams,
        sports_leagues=user_settings.sports_leagues,
        weather_locations=user_settings.weather_locations,
        fun_segments=user_settings.fun_segments,
        briefing_length=user_settings.briefing_length,
        include_intro_music=user_settings.include_intro_music,
        include_transitions=user_settings.include_transitions,
        news_exclusions=user_settings.news_exclusions or [],
        voice_id=user_settings.voice_id,
        voice_style=user_settings.voice_style,
        voice_speed=user_settings.voice_speed,
        tts_provider=getattr(user_settings, 'tts_provider', None) or "elevenlabs",
        segment_order=user_settings.segment_order or ["news", "sports", "weather", "fun"],
        include_music=user_settings.include_music or False,
        writing_style=getattr(user_settings, 'writing_style', None) or "good_morning_america",
        timezone=getattr(user_settings, 'timezone', None) or "America/New_York",
        deep_dive_enabled=getattr(user_settings, 'deep_dive_enabled', False),
        updated_at=user_settings.updated_at,
    )

    return JSONResponse(response.model_dump(mode='json'))
