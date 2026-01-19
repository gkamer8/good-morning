"""Voice API endpoints."""

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import edge_tts
from src.audio.tts import (
    VOICES,
    TTSProvider,
    ChatterboxCloneVoice,
    ChatterboxPredefinedVoice,
)
from src.config import get_settings


router = APIRouter()
settings = get_settings()

PREVIEW_TEXT = "Good morning! This is your Morning Drive briefing for today. Let's get you caught up on what's happening."


class VoiceResponse(BaseModel):
    """API response for a voice."""

    voice_key: str
    provider: str
    display_name: str
    description: str | None = None


class VoiceListResponse(BaseModel):
    """API response for voice list."""

    voices: list[VoiceResponse]
    total: int


@router.get("/voices", response_model=VoiceListResponse)
async def list_voices_endpoint(provider: TTSProvider | None = None):
    """List all available voices, optionally filtered by provider."""
    if provider:
        voices = {k: v for k, v in VOICES.items() if v.provider == provider}
    else:
        voices = VOICES

    response_voices = []
    for voice_key, voice in voices.items():
        description = None
        if hasattr(voice, "description"):
            description = voice.description

        response_voices.append(
            VoiceResponse(
                voice_key=voice_key,
                provider=voice.provider,
                display_name=voice.display_name,
                description=description,
            )
        )

    return VoiceListResponse(voices=response_voices, total=len(response_voices))


@router.get("/voices/{voice_key}")
async def get_voice_endpoint(voice_key: str):
    """Get details for a specific voice."""
    voice = VOICES.get(voice_key)
    if voice is None:
        raise HTTPException(status_code=404, detail=f"Voice not found: {voice_key}")

    description = None
    if hasattr(voice, "description"):
        description = voice.description

    return VoiceResponse(
        voice_key=voice_key,
        provider=voice.provider,
        display_name=voice.display_name,
        description=description,
    )


@router.get("/voices/{voice_key}/preview")
async def get_voice_preview(voice_key: str):
    """Get or generate a voice preview audio sample."""
    voice = VOICES.get(voice_key)
    if voice is None:
        raise HTTPException(status_code=404, detail=f"Voice not found: {voice_key}")

    preview_dir = settings.assets_dir / "audio" / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)

    preview_path = preview_dir / f"{voice_key}.mp3"

    if not preview_path.exists():
        raise FileNotFoundError(f"Preview for {voice_key} not found")

    return FileResponse(
        preview_path,
        media_type="audio/mpeg",
        filename=f"voice_preview_{voice_key}.mp3",
    )
