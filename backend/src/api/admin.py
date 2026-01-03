"""Admin interface routes for Morning Drive."""

import socket
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.storage.database import MusicPiece, get_session
from src.storage.minio_storage import get_minio_storage


def get_server_ip() -> str:
    """Get the server's local IP address."""
    try:
        # Create a socket to determine the local IP
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
            <a href="/">Home</a>
            <a href="/docs/getting-started">Docs</a>
            <a href="/admin/logout">Sign Out</a>
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
                        <label for="description">Description</label>
                        <textarea id="description" name="description" placeholder="Interesting facts about this piece..."></textarea>
                        <p class="help">This will be read by the host to introduce the music.</p>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="duration">Duration (seconds) *</label>
                            <input type="number" id="duration" name="duration_seconds" required min="1" placeholder="e.g., 360">
                        </div>
                        <div class="form-group">
                            <label for="file">Audio File (MP3) *</label>
                            <input type="file" id="file" name="file" accept="audio/mpeg,audio/mp3" required>
                        </div>
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
    duration_seconds: float = Form(...),
    file: UploadFile = None,
    description: str = Form(None),
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
            url=f"/admin/music?success=Uploaded+{title}+successfully",
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
