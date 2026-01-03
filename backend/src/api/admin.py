"""Admin interface routes for Morning Drive."""

import asyncio
import io
import socket
import time
from datetime import datetime
from typing import Optional

import anthropic
import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from pydub import AudioSegment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.storage.database import MusicPiece, get_session
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
    "CNBC Market Data": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
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
        # Try to list objects (lightweight operation) - use storage.bucket not bucket_name
        files = await storage.list_files(prefix="")
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

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    prompt = f"""Write a brief, engaging introduction for a classical music piece that a radio host would read before playing it. Keep it to 2-3 sentences.

Title: {title}
Composer: {composer}

Include one or two interesting facts about the piece or composer. Make it conversational and suitable for a morning radio show. Do not include any prefixes like "Here's" or "And now" - just the interesting content."""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"Failed to generate music description: {e}")
        return ""


def get_server_ip() -> str:
    """Get the server's IP address that clients can connect to.

    When running in Docker, this tries to get the host machine's IP
    rather than the container's internal IP.
    """
    import os

    # First check for explicit override via environment variable
    if os.environ.get("SERVER_IP"):
        return os.environ["SERVER_IP"]

    # Try to resolve host.docker.internal (works on Docker Desktop for Mac/Windows)
    try:
        ip = socket.gethostbyname("host.docker.internal")
        return ip
    except socket.gaierror:
        pass

    # Fall back to detecting via socket connection
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "Unable to determine"

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


@router.get("/", response_class=HTMLResponse)
async def admin_index(request: Request):
    """Admin index - redirect to login or music page."""
    if is_authenticated(request):
        return RedirectResponse(url="/admin/music", status_code=302)
    return RedirectResponse(url="/admin/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request, error: str = None):
    """Admin login page."""
    error_html = ""
    if error:
        error_html = f'<div class="error">{error}</div>'

    return HTMLResponse(content=f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - Morning Drive</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .login-box {{
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
        }}
        h1 {{
            text-align: center;
            margin-bottom: 8px;
            color: #333;
        }}
        .subtitle {{
            text-align: center;
            color: #666;
            margin-bottom: 32px;
        }}
        .error {{
            background: #fee;
            color: #c00;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }}
        label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #333;
        }}
        input[type="password"] {{
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            margin-bottom: 20px;
            transition: border-color 0.2s;
        }}
        input[type="password"]:focus {{
            outline: none;
            border-color: #667eea;
        }}
        button {{
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }}
    </style>
</head>
<body>
    <div class="login-box">
        <h1>Morning Drive</h1>
        <p class="subtitle">Admin Panel</p>
        {error_html}
        <form method="POST" action="/admin/login">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required autofocus>
            <button type="submit">Sign In</button>
        </form>
    </div>
</body>
</html>
""")


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


@router.get("/music", response_class=HTMLResponse)
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

    # Build the pieces table rows
    pieces_html = ""
    for p in pieces:
        status_badge = '<span class="badge active">Active</span>' if p.is_active else '<span class="badge inactive">Inactive</span>'
        size_mb = f"{p.file_size_bytes / 1024 / 1024:.1f} MB" if p.file_size_bytes else "Unknown"
        duration_min = f"{p.duration_seconds / 60:.1f} min"
        pieces_html += f"""
        <tr>
            <td><strong>{p.title}</strong><br><span class="composer">{p.composer}</span></td>
            <td>{duration_min}</td>
            <td>{size_mb}</td>
            <td>{status_badge}</td>
            <td>
                <form method="POST" action="/admin/music/{p.id}/delete" style="display:inline;">
                    <button type="submit" class="btn-delete" onclick="return confirm('Delete {p.title}?')">Delete</button>
                </form>
            </td>
        </tr>
        """

    if not pieces:
        pieces_html = '<tr><td colspan="5" class="empty">No music pieces yet. Upload one below!</td></tr>'

    # Messages
    messages_html = ""
    if success:
        messages_html += f'<div class="message success">{success}</div>'
    if error:
        messages_html += f'<div class="message error">{error}</div>'

    # Get server IP for app connection
    server_ip = get_server_ip()
    server_url = f"http://{server_ip}:{settings.port}"

    return HTMLResponse(content=f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Music Management - Morning Drive Admin</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f7fa;
            min-height: 100vh;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .header h1 {{ font-size: 1.5rem; }}
        .header a {{
            color: white;
            text-decoration: none;
            opacity: 0.9;
        }}
        .header a:hover {{ opacity: 1; }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 40px 20px;
        }}
        .card {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            margin-bottom: 30px;
            overflow: hidden;
        }}
        .card-header {{
            padding: 20px 24px;
            border-bottom: 1px solid #eee;
            font-weight: 600;
            font-size: 1.1rem;
        }}
        .card-body {{ padding: 24px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 14px 16px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
            font-size: 0.9rem;
            color: #666;
        }}
        .composer {{ color: #666; font-size: 0.9rem; }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
        }}
        .badge.active {{ background: #d4edda; color: #155724; }}
        .badge.inactive {{ background: #f8d7da; color: #721c24; }}
        .btn-delete {{
            padding: 6px 12px;
            background: #dc3545;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.85rem;
        }}
        .btn-delete:hover {{ background: #c82333; }}
        .empty {{
            text-align: center;
            color: #666;
            padding: 40px !important;
        }}
        .form-group {{
            margin-bottom: 20px;
        }}
        label {{
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #333;
        }}
        input[type="text"], input[type="number"], textarea {{
            width: 100%;
            padding: 10px 14px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
        }}
        input[type="file"] {{
            padding: 10px 0;
        }}
        textarea {{ resize: vertical; min-height: 80px; }}
        .form-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        .btn-primary {{
            padding: 12px 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
        }}
        .btn-primary:hover {{
            opacity: 0.9;
        }}
        .message {{
            padding: 14px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }}
        .message.success {{ background: #d4edda; color: #155724; }}
        .message.error {{ background: #f8d7da; color: #721c24; }}
        .help {{ font-size: 0.85rem; color: #666; margin-top: 6px; }}
    </style>
</head>
<body>
    <div class="header">
        <a href="/" style="text-decoration:none;"><h1>Morning Drive Admin</h1></a>
        <nav style="display:flex;gap:20px;align-items:center;">
            <a href="/admin/music" style="background: rgba(255,255,255,0.15); padding: 6px 12px; border-radius: 4px;">Music</a>
            <a href="/admin/health" style="padding: 6px 12px; border-radius: 4px;">Health</a>
            <a href="/" style="padding: 6px 12px; border-radius: 4px;">Home</a>
            <a href="/docs/getting-started" style="padding: 6px 12px; border-radius: 4px;">Docs</a>
            <a href="/admin/logout" style="padding: 6px 12px; border-radius: 4px;">Sign Out</a>
        </nav>
    </div>
    <div class="container">
        {messages_html}

        <div class="card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;">
            <div class="card-body" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
                <div>
                    <div style="font-size: 0.85rem; opacity: 0.9; margin-bottom: 4px;">App Server URL</div>
                    <div style="font-size: 1.4rem; font-weight: 600; font-family: monospace;">{server_url}</div>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 0.85rem; opacity: 0.9;">Enter this URL in the Morning Drive app settings to connect</div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">Music Library</div>
            <table>
                <thead>
                    <tr>
                        <th>Title / Composer</th>
                        <th>Duration</th>
                        <th>Size</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {pieces_html}
                </tbody>
            </table>
        </div>

        <div class="card">
            <div class="card-header">Upload New Music</div>
            <div class="card-body">
                <form method="POST" action="/admin/music/upload" enctype="multipart/form-data">
                    <div class="form-row">
                        <div class="form-group">
                            <label for="title">Title *</label>
                            <input type="text" id="title" name="title" required placeholder="e.g., Moonlight Sonata">
                        </div>
                        <div class="form-group">
                            <label for="composer">Composer *</label>
                            <input type="text" id="composer" name="composer" required placeholder="e.g., Ludwig van Beethoven">
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="file">Audio File (MP3) *</label>
                        <input type="file" id="file" name="file" accept="audio/mpeg,audio/mp3" required>
                        <p class="help" style="margin-top: 8px; color: #666;">
                            Duration will be auto-detected from the audio file.<br>
                            An introduction will be auto-generated by AI based on the title and composer.
                        </p>
                    </div>
                    <button type="submit" class="btn-primary">Upload Music</button>
                </form>
            </div>
        </div>
    </div>
</body>
</html>
""")


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
        # Auto-detect duration from audio file
        try:
            duration_seconds = get_audio_duration(content)
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


@router.get("/health", response_class=HTMLResponse)
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

    def render_status_badge(result):
        """Render a status badge for a health check result."""
        if isinstance(result, Exception):
            return '<span class="badge error">Exception</span>'
        status = result.get("status", "unknown")
        if status == "ok":
            return '<span class="badge ok">OK</span>'
        elif status == "configured":
            return '<span class="badge configured">Configured</span>'
        elif status == "not_configured":
            return '<span class="badge warning">Not Configured</span>'
        elif status == "timeout":
            return '<span class="badge warning">Timeout</span>'
        else:
            return '<span class="badge error">Error</span>'

    def render_result_row(result):
        """Render a table row for a health check result."""
        if isinstance(result, Exception):
            return f"""
            <tr>
                <td>Unknown</td>
                <td><span class="badge error">Exception</span></td>
                <td>-</td>
                <td class="error-text">{str(result)[:100]}</td>
            </tr>
            """
        name = result.get("name", "Unknown")
        status_badge = render_status_badge(result)
        response_time = result.get("response_time_ms", 0)
        time_class = "fast" if response_time < 500 else ("slow" if response_time > 2000 else "")
        error = result.get("error", "")
        return f"""
        <tr>
            <td><strong>{name}</strong></td>
            <td>{status_badge}</td>
            <td class="{time_class}">{response_time}ms</td>
            <td class="error-text">{error or '-'}</td>
        </tr>
        """

    # Build HTML tables
    rss_rows = "".join(render_result_row(r) for r in rss_results)
    api_rows = "".join(render_result_row(r) for r in api_results)
    internal_rows = "".join(render_result_row(r) for r in internal_results)

    # Calculate overall status
    all_statuses = [r.get("status") if not isinstance(r, Exception) else "error" for r in all_results]
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

    return HTMLResponse(content=f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Health Check - Morning Drive Admin</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f7fa;
            min-height: 100vh;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .header h1 {{ font-size: 1.5rem; }}
        .header nav {{
            display: flex;
            gap: 20px;
            align-items: center;
        }}
        .header a {{
            color: white;
            text-decoration: none;
            opacity: 0.9;
            padding: 6px 12px;
            border-radius: 4px;
            transition: background 0.2s;
        }}
        .header a:hover {{
            opacity: 1;
            background: rgba(255,255,255,0.15);
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 40px 20px;
        }}
        .status-banner {{
            padding: 20px 24px;
            border-radius: 12px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .status-banner.ok {{
            background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
            color: white;
        }}
        .status-banner.warning {{
            background: linear-gradient(135deg, #ffc107 0%, #fd7e14 100%);
            color: #333;
        }}
        .status-banner.error {{
            background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
            color: white;
        }}
        .status-banner h2 {{ font-size: 1.3rem; margin-bottom: 4px; }}
        .status-banner .stats {{
            display: flex;
            gap: 20px;
            font-size: 0.9rem;
        }}
        .card {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            margin-bottom: 30px;
            overflow: hidden;
        }}
        .card-header {{
            padding: 20px 24px;
            border-bottom: 1px solid #eee;
            font-weight: 600;
            font-size: 1.1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .card-header .count {{
            font-weight: normal;
            color: #666;
            font-size: 0.9rem;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 14px 16px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
            font-size: 0.85rem;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
        }}
        .badge.ok {{ background: #d4edda; color: #155724; }}
        .badge.configured {{ background: #cce5ff; color: #004085; }}
        .badge.warning {{ background: #fff3cd; color: #856404; }}
        .badge.error {{ background: #f8d7da; color: #721c24; }}
        .error-text {{ color: #dc3545; font-size: 0.9rem; }}
        .fast {{ color: #28a745; }}
        .slow {{ color: #dc3545; }}
        .refresh-btn {{
            padding: 10px 20px;
            background: white;
            color: #667eea;
            border: 2px solid currentColor;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
        }}
        .refresh-btn:hover {{
            background: #667eea;
            color: white;
        }}
        .timestamp {{
            text-align: center;
            color: #666;
            font-size: 0.85rem;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <a href="/" style="text-decoration:none;"><h1>Morning Drive Admin</h1></a>
        <nav>
            <a href="/admin/music">Music</a>
            <a href="/admin/health" style="background: rgba(255,255,255,0.15);">Health</a>
            <a href="/">Home</a>
            <a href="/docs/getting-started">Docs</a>
            <a href="/admin/logout">Sign Out</a>
        </nav>
    </div>
    <div class="container">
        <div class="status-banner {overall_status}">
            <div>
                <h2>{overall_text}</h2>
                <div class="stats">
                    <span>{ok_count}/{total} services healthy</span>
                </div>
            </div>
            <a href="/admin/health" class="refresh-btn">Refresh</a>
        </div>

        <div class="card">
            <div class="card-header">
                RSS News Feeds
                <span class="count">{len(rss_results)} sources</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Source</th>
                        <th>Status</th>
                        <th>Response Time</th>
                        <th>Error</th>
                    </tr>
                </thead>
                <tbody>
                    {rss_rows}
                </tbody>
            </table>
        </div>

        <div class="card">
            <div class="card-header">
                External APIs
                <span class="count">{len(api_results)} services</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Service</th>
                        <th>Status</th>
                        <th>Response Time</th>
                        <th>Error</th>
                    </tr>
                </thead>
                <tbody>
                    {api_rows}
                </tbody>
            </table>
        </div>

        <div class="card">
            <div class="card-header">
                Internal Services
                <span class="count">{len(internal_results)} services</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Service</th>
                        <th>Status</th>
                        <th>Response Time</th>
                        <th>Error</th>
                    </tr>
                </thead>
                <tbody>
                    {internal_rows}
                </tbody>
            </table>
        </div>

        <p class="timestamp">Last checked: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
</body>
</html>
""")
