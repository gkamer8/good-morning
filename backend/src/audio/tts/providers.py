"""TTS provider implementations (ElevenLabs, Edge TTS, Chatterbox)."""

import asyncio
from pathlib import Path

import edge_tts
import httpx
from elevenlabs import ElevenLabs
from pydub import AudioSegment as PydubSegment

from src.config import get_settings

from .profiles import CHATTERBOX_VOICE_PROFILES, DEFAULT_CHATTERBOX_VOICE


async def generate_audio_edge_tts(
    text: str,
    voice: str,
    output_path: Path,
    voice_speed: float = 1.0,
) -> float:
    """Generate audio using Edge TTS (Microsoft TTS).

    Args:
        text: Text to convert to speech
        voice: Edge TTS voice name (e.g., "en-US-GuyNeural")
        output_path: Path to save the audio file
        voice_speed: Speed multiplier (1.0 = normal)

    Returns:
        Duration in seconds
    """
    if voice_speed != 1.0:
        rate_percent = int((voice_speed - 1.0) * 100)
        rate = f"{rate_percent:+d}%"
    else:
        rate = "+0%"

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(output_path))

    audio = PydubSegment.from_mp3(output_path)
    duration_seconds = len(audio) / 1000.0

    return duration_seconds


async def generate_audio_chatterbox(
    text: str,
    voice_id: str,
    output_path: Path,
) -> float:
    """Generate audio using Chatterbox TTS (self-hosted).

    Args:
        text: Text to convert to speech
        voice_id: Chatterbox voice ID (e.g., "timmy", "austin", "alice")
        output_path: Path to save the audio file

    Returns:
        Duration in seconds
    """
    settings = get_settings()

    voice_config = CHATTERBOX_VOICE_PROFILES.get(
        voice_id.lower(),
        CHATTERBOX_VOICE_PROFILES[DEFAULT_CHATTERBOX_VOICE]
    )

    payload = {
        "text": text,
        "voice_mode": voice_config["voice_mode"],
        "output_format": "mp3",
        "split_text": True,
        "chunk_size": 500,
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


async def generate_audio_elevenlabs(
    text: str,
    voice_id: str,
    output_path: Path,
    client: ElevenLabs,
    voice_style: str = "energetic",
    voice_speed: float = 1.1,
) -> float:
    """Generate audio using ElevenLabs.

    Args:
        text: Text to convert to speech
        voice_id: ElevenLabs voice ID
        output_path: Path to save the audio file
        client: ElevenLabs client
        voice_style: Style of delivery (energetic, calm, professional)
        voice_speed: Speed multiplier (1.0 = normal)

    Returns:
        Duration in seconds
    """
    settings = get_settings()

    voice_settings_map = {
        "energetic": {
            "stability": 0.35,
            "similarity_boost": 0.75,
            "style": 0.65,
            "use_speaker_boost": True,
        },
        "professional": {
            "stability": 0.60,
            "similarity_boost": 0.80,
            "style": 0.30,
            "use_speaker_boost": True,
        },
        "calm": {
            "stability": 0.75,
            "similarity_boost": 0.70,
            "style": 0.15,
            "use_speaker_boost": False,
        },
    }

    style_config = voice_settings_map.get(voice_style, voice_settings_map["energetic"])

    def generate_sync():
        audio_generator = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=settings.elevenlabs_model_id,
            output_format="mp3_44100_128",
            voice_settings={
                "stability": style_config["stability"],
                "similarity_boost": style_config["similarity_boost"],
                "style": style_config["style"],
                "use_speaker_boost": style_config["use_speaker_boost"],
            },
        )
        with open(output_path, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)

    await asyncio.to_thread(generate_sync)

    audio = PydubSegment.from_mp3(output_path)

    if voice_speed != 1.0 and 0.5 <= voice_speed <= 2.0:
        audio = audio.speedup(playback_speed=voice_speed)
        audio.export(output_path, format="mp3")

    duration_seconds = len(audio) / 1000.0

    return duration_seconds

