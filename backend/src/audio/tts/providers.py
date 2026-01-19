"""TTS provider implementations (Edge TTS and Chatterbox).

Provider functions receive a Voice object and introspect it ONCE
to extract the API-specific parameters.
"""

from pathlib import Path

import edge_tts
import httpx
from pydub import AudioSegment as PydubSegment

from src.config import get_settings

from .voice import (
    ChatterboxCloneVoice,
    ChatterboxPredefinedVoice,
    EdgeVoice,
)


async def generate_audio_edge_tts(
    text: str,
    voice: EdgeVoice,
    output_path: Path,
) -> float:
    """Generate audio using Edge TTS (Microsoft TTS).

    Args:
        text: Text to convert to speech
        voice: Edge voice configuration (introspected HERE for API params)
        output_path: Path to save the audio file
        voice_speed: Speed multiplier (1.0 = normal)

    Returns:
        Duration in seconds
    """
    # INTROSPECTION POINT: Extract API-specific parameter
    voice_name = voice.voice_name
    communicate = edge_tts.Communicate(text, voice_name, rate=1.0)
    await communicate.save(str(output_path))

    audio = PydubSegment.from_mp3(output_path)
    duration_seconds = len(audio) / 1000.0

    return duration_seconds


async def generate_audio_chatterbox(
    text: str,
    voice: ChatterboxCloneVoice | ChatterboxPredefinedVoice,
    output_path: Path,
) -> float:
    """Generate audio using Chatterbox TTS (self-hosted).

    Args:
        text: Text to convert to speech
        voice: Chatterbox voice configuration (introspected HERE for API params)
        output_path: Path to save the audio file

    Returns:
        Duration in seconds
    """
    settings = get_settings()

    # INTROSPECTION POINT: Extract API-specific parameters based on mode
    payload = {
        "text": text,
        "voice_mode": voice.mode,
        "output_format": "mp3",
        "split_text": True,
        "chunk_size": 500,
        "temperature": 0.7,
        "exaggeration": 0.7,
        "cfg_weight": 0.5,
        "seed": 1986,
    }

    if voice.mode == "clone":
        payload["reference_audio_filename"] = voice.reference_audio_filename
    else:
        payload["predefined_voice_id"] = voice.predefined_voice_id

    chatterbox_url = settings.chatterbox_url

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(f"{chatterbox_url}/tts", json=payload)
            response.raise_for_status()
        except httpx.ConnectError:
            chatterbox_url = settings.chatterbox_dev_url
            response = await client.post(f"{chatterbox_url}/tts", json=payload)
            response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(response.content)

    audio = PydubSegment.from_mp3(output_path)
    duration_seconds = len(audio) / 1000.0

    return duration_seconds
