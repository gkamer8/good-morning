"""Admin music management routes."""

import asyncio
import io
import os
import socket

import anthropic
from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydub import AudioSegment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import CLAUDE_MODEL
from src.api.template_config import templates
from src.config import get_settings
from src.prompts import render_prompt
from src.storage.database import MusicPiece, get_session
from src.storage.minio_storage import get_minio_storage


settings = get_settings()
router = APIRouter()


def get_audio_duration(audio_bytes: bytes) -> float:
    """Extract duration in seconds from audio file bytes."""
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
    return len(audio) / 1000.0


async def generate_music_description(title: str, composer: str) -> str:
    """Generate an interesting description for a classical music piece using Claude."""
    if not settings.anthropic_api_key:
        return ""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    prompt = render_prompt(
        "music_description.jinja2",
        title=title,
        composer=composer,
    )

    try:
        message = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"Failed to generate music description: {e}")
        return ""


def get_server_url() -> str | None:
    """Get the server's URL that clients can connect to."""
    if os.environ.get("SERVER_IP"):
        return f"http://{os.environ['SERVER_IP']}:{settings.port}"

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()

        if ip.startswith("192.168.65.") or ip.startswith("172.17.") or ip.startswith("172.18."):
            return None

        return f"http://{ip}:{settings.port}"
    except Exception:
        return None


@router.get("/music")
async def admin_music_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    success: str = None,
    error: str = None,
):
    """Admin music management page."""
    from . import is_authenticated
    
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    result = await session.execute(
        select(MusicPiece).order_by(MusicPiece.composer, MusicPiece.title)
    )
    pieces = result.scalars().all()
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
    from . import is_authenticated
    
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    if not file:
        return RedirectResponse(url="/admin/music?error=No+file+provided", status_code=302)

    if not file.content_type or not file.content_type.startswith("audio/"):
        return RedirectResponse(url="/admin/music?error=File+must+be+an+audio+file", status_code=302)

    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title).strip()
    safe_composer = "".join(c if c.isalnum() or c in " -_" else "" for c in composer).strip()
    s3_key = f"music/{safe_composer}/{safe_title}.mp3".replace(" ", "_").lower()

    content = await file.read()
    if len(content) < 10000:
        return RedirectResponse(url="/admin/music?error=File+too+small+to+be+valid+audio", status_code=302)

    try:
        try:
            duration_seconds = await asyncio.to_thread(get_audio_duration, content)
        except Exception as e:
            print(f"Failed to detect audio duration: {e}")
            return RedirectResponse(
                url="/admin/music?error=Could+not+read+audio+file.+Make+sure+it's+a+valid+MP3.",
                status_code=302
            )

        description = await generate_music_description(title, composer)

        storage = get_minio_storage()
        await storage.ensure_bucket_exists()
        result = await storage.upload_bytes(content, s3_key, content_type=file.content_type or "audio/mpeg")

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
    from . import is_authenticated
    
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/login", status_code=302)

    result = await session.execute(select(MusicPiece).where(MusicPiece.id == piece_id))
    piece = result.scalar_one_or_none()

    if not piece:
        return RedirectResponse(url="/admin/music?error=Music+piece+not+found", status_code=302)

    title = piece.title

    try:
        storage = get_minio_storage()
        await storage.delete_file(piece.s3_key)
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

