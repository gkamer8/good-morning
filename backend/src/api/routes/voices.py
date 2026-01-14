"""Voice API endpoints."""

import httpx
from elevenlabs import ElevenLabs
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.audio.tts import list_available_voices, CHATTERBOX_VOICE_PROFILES
from src.config import get_settings


router = APIRouter()
settings = get_settings()

# Stock ElevenLabs voice IDs (Rachel, Adam, Arnold)
STOCK_VOICE_IDS = {
    "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "pNInz6obpgDQGcFmaJgB",  # Adam
    "VR6AewLTigWG4xSOukaG",  # Arnold
}
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel

# Chatterbox voice IDs (self-hosted TTS)
CHATTERBOX_VOICE_IDS = {"timmy", "austin", "alice"}
DEFAULT_CHATTERBOX_VOICE_ID = "timmy"

PREVIEW_TEXT = "Good morning! This is your Morning Drive briefing for today. Let's get you caught up on what's happening."


def get_valid_voice_ids(tts_provider: str = "elevenlabs") -> set:
    """Get all valid voice IDs for a given TTS provider."""
    if tts_provider == "chatterbox":
        return CHATTERBOX_VOICE_IDS
    elif tts_provider == "edge":
        return set()
    else:
        custom_voice_ids = set(settings.elevenlabs_custom_voice_ids or [])
        return STOCK_VOICE_IDS | custom_voice_ids


@router.get("/voices")
async def list_voices(tts_provider: str = "elevenlabs"):
    """List all available voices for the specified TTS provider."""
    if tts_provider == "chatterbox":
        voices = [
            {
                "voice_id": voice_id,
                "name": config["display_name"],
                "description": config["description"],
                "labels": {"provider": "chatterbox"},
            }
            for voice_id, config in CHATTERBOX_VOICE_PROFILES.items()
            if voice_id != "host"
        ]
        return {"voices": voices, "total": len(voices)}
    elif tts_provider == "edge":
        return {"voices": [], "total": 0}
    else:
        voices = await list_available_voices()
        return {"voices": voices, "total": len(voices)}


@router.get("/voices/{voice_id}/preview")
async def get_voice_preview(voice_id: str):
    """Get or generate a voice preview audio sample."""
    preview_dir = settings.audio_output_dir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)

    is_chatterbox_voice = voice_id.lower() in CHATTERBOX_VOICE_IDS

    if is_chatterbox_voice:
        preview_path = preview_dir / f"chatterbox_{voice_id.lower()}.mp3"
    else:
        preview_path = preview_dir / f"{voice_id}.mp3"

    needs_generation = False
    if not preview_path.exists():
        needs_generation = True
    elif preview_path.stat().st_size == 0:
        preview_path.unlink()
        needs_generation = True

    if needs_generation:
        if is_chatterbox_voice:
            try:
                voice_config = CHATTERBOX_VOICE_PROFILES.get(
                    voice_id.lower(),
                    CHATTERBOX_VOICE_PROFILES["timmy"]
                )

                payload = {
                    "text": PREVIEW_TEXT,
                    "voice_mode": voice_config["voice_mode"],
                    "output_format": "mp3",
                    "split_text": False,
                    "temperature": 0.7,
                    "exaggeration": 0.7,
                    "cfg_weight": 0.5,
                    "seed": 1986,
                }

                if voice_config["voice_mode"] == "clone":
                    payload["reference_audio_filename"] = voice_config["reference_audio_filename"]
                else:
                    payload["predefined_voice_id"] = voice_config["predefined_voice_id"]

                chatterbox_url = settings.chatterbox_url
                async with httpx.AsyncClient(timeout=60.0) as client:
                    try:
                        response = await client.post(f"{chatterbox_url}/tts", json=payload)
                        response.raise_for_status()
                    except httpx.ConnectError:
                        chatterbox_url = settings.chatterbox_dev_url
                        response = await client.post(f"{chatterbox_url}/tts", json=payload)
                        response.raise_for_status()

                    temp_path = preview_dir / f"chatterbox_{voice_id.lower()}.tmp.mp3"
                    with open(temp_path, "wb") as f:
                        f.write(response.content)

                    if temp_path.stat().st_size == 0:
                        temp_path.unlink()
                        raise HTTPException(
                            status_code=500,
                            detail=f"Chatterbox returned empty audio for voice {voice_id}"
                        )

                    temp_path.rename(preview_path)

            except HTTPException:
                raise
            except Exception as e:
                if preview_path.exists() and preview_path.stat().st_size == 0:
                    preview_path.unlink()
                raise HTTPException(status_code=500, detail=f"Failed to generate Chatterbox preview: {str(e)}")
        else:
            if not settings.elevenlabs_api_key:
                raise HTTPException(status_code=500, detail="ElevenLabs API key not configured")

            try:
                client = ElevenLabs(api_key=settings.elevenlabs_api_key)

                audio_generator = client.text_to_speech.convert(
                    voice_id=voice_id,
                    text=PREVIEW_TEXT,
                    model_id=settings.elevenlabs_model_id,
                    output_format="mp3_44100_128",
                    voice_settings={
                        "stability": 0.35,
                        "similarity_boost": 0.75,
                        "style": 0.65,
                        "use_speaker_boost": True,
                    },
                )

                temp_path = preview_dir / f"{voice_id}.tmp.mp3"
                bytes_written = 0
                with open(temp_path, "wb") as f:
                    for chunk in audio_generator:
                        f.write(chunk)
                        bytes_written += len(chunk)

                if bytes_written == 0:
                    temp_path.unlink()
                    raise HTTPException(
                        status_code=500,
                        detail=f"ElevenLabs returned empty audio for voice {voice_id}"
                    )

                temp_path.rename(preview_path)
            finally:
                if preview_path.exists() and preview_path.stat().st_size == 0:
                    preview_path.unlink()

    return FileResponse(
        preview_path,
        media_type="audio/mpeg",
        filename=f"voice_preview_{voice_id}.mp3",
    )

