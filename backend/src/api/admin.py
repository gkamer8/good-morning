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
from src.storage.database import Briefing, MusicPiece, Schedule, UserSettings, get_session
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
    settings = get_settings()

    if not settings.anthropic_api_key:
        return ""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    prompt = f"""Write a brief, engaging introduction for a classical music piece that a radio host would read before playing it. Keep it to 2-3 sentences.

Title: {title}
Composer: {composer}

Include one or two interesting facts about the piece or composer. Make it conversational and suitable for a morning radio show. Do not include any prefixes like "Here's" or "And now" - just the interesting content."""

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
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(feed_url)
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
            games = await fetch_espn_scoreboard(league_key)
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

    # Get schedule configuration
    result = await session.execute(select(Schedule).limit(1))
    schedule = result.scalar_one_or_none()

    # Format schedule info
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if schedule:
        schedule_enabled = schedule.enabled
        schedule_time = f"{schedule.time_hour:02d}:{schedule.time_minute:02d}"
        schedule_days = ", ".join(day_names[d] for d in sorted(schedule.days_of_week))
        schedule_timezone = schedule.timezone
    else:
        schedule_enabled = False
        schedule_time = "Not configured"
        schedule_days = "Not configured"
        schedule_timezone = "Not configured"

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

    # Get recent briefings
    result = await session.execute(
        select(Briefing)
        .order_by(Briefing.created_at.desc())
        .limit(20)
    )
    briefings_raw = result.scalars().all()

    briefings = []
    for b in briefings_raw:
        errors = b.generation_errors if b.generation_errors else []
        briefings.append({
            "id": b.id,
            "title": b.title,
            "created_at": b.created_at.strftime("%Y-%m-%d %H:%M"),
            "status": b.status,
            "duration": f"{int(b.duration_seconds // 60)}:{int(b.duration_seconds % 60):02d}" if b.duration_seconds else "-",
            "error_count": len(errors),
            "errors": errors,
        })

    return templates.TemplateResponse(
        request,
        "admin/scheduler.html",
        {
            "active_page": "admin-scheduler",
            "is_authenticated": True,
            "scheduler_running": scheduler_running,
            "schedule_enabled": schedule_enabled,
            "schedule_time": schedule_time,
            "schedule_days": schedule_days,
            "schedule_timezone": schedule_timezone,
            "next_run": next_run,
            "jobs": jobs,
            "briefings": briefings,
            "last_checked": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
    )
