"""TTS integration with ElevenLabs, Edge TTS, and Chatterbox support."""

import asyncio
import hashlib
from typing import Optional

from elevenlabs import ElevenLabs
from pydub import AudioSegment as PydubSegment

from src.api.schemas import BriefingScript
from src.config import get_settings

from .models import AudioSegment, TTSError, TTSResult
from .profiles import (
    CHATTERBOX_VOICE_PROFILES,
    DEFAULT_CHATTERBOX_VOICE,
    DEFAULT_EDGE_VOICE,
    EDGE_VOICE_PROFILES,
    match_voice_to_profile,
)
from .providers import (
    generate_audio_chatterbox,
    generate_audio_edge_tts,
    generate_audio_elevenlabs,
)


# Re-export for backwards compatibility
__all__ = [
    "AudioSegment",
    "TTSError",
    "TTSResult",
    "CHATTERBOX_VOICE_PROFILES",
    "DEFAULT_CHATTERBOX_VOICE",
    "DEFAULT_EDGE_VOICE",
    "EDGE_VOICE_PROFILES",
    "match_voice_to_profile",
    "generate_audio_for_script",
    "list_available_voices",
]


async def generate_audio_for_script(
    script: BriefingScript,
    voice_id: Optional[str] = None,
    voice_style: str = "energetic",
    voice_speed: float = 1.1,
    tts_provider: str = "elevenlabs",
) -> TTSResult:
    """Generate audio for all segments in a script.

    Args:
        script: The briefing script to generate audio for
        voice_id: Override voice ID for host (uses settings default if None)
        voice_style: Style of delivery (energetic, calm, professional)
        voice_speed: Speed multiplier (1.0 = normal)
        tts_provider: TTS provider ("elevenlabs", "edge", or "chatterbox")

    Returns:
        TTSResult with audio segments, any errors, and validation info
    """
    settings = get_settings()

    client = None
    if tts_provider == "elevenlabs":
        if not settings.elevenlabs_api_key:
            raise ValueError("ELEVENLABS_API_KEY not configured")
        client = ElevenLabs(api_key=settings.elevenlabs_api_key)
        host_voice_id = voice_id or settings.elevenlabs_host_voice_id
    elif tts_provider == "chatterbox":
        host_voice_id = voice_id or DEFAULT_CHATTERBOX_VOICE
    else:
        host_voice_id = EDGE_VOICE_PROFILES.get("host", DEFAULT_EDGE_VOICE)

    temp_dir = settings.audio_output_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    audio_segments = []
    errors = []
    segment_index = 0

    expected_segment_types = {seg.type for seg in script.segments if seg.items}

    print(f"Generating audio with provider={tts_provider}, voice_style={voice_style}, voice_speed={voice_speed}")
    print(f"Expected segment types: {expected_segment_types}")

    for seg_idx, segment in enumerate(script.segments):
        segment_has_audio = False

        for item_idx, item in enumerate(segment.items):
            if not item.text.strip():
                continue

            if item.voice == "host":
                current_voice_id = host_voice_id
            else:
                current_voice_id = match_voice_to_profile(item.voice_profile, provider=tts_provider)

            content_key = f"{item.text}{current_voice_id}{voice_style}{voice_speed}{tts_provider}"
            text_hash = hashlib.md5(content_key.encode()).hexdigest()[:8]
            filename = f"seg_{seg_idx:02d}_{item_idx:02d}_{text_hash}.mp3"
            output_path = temp_dir / filename

            if output_path.exists():
                audio = PydubSegment.from_mp3(output_path)
                duration = len(audio) / 1000.0
                segment_has_audio = True
            else:
                try:
                    if tts_provider == "edge":
                        duration = await generate_audio_edge_tts(
                            text=item.text,
                            voice=current_voice_id,
                            output_path=output_path,
                            voice_speed=voice_speed,
                        )
                    elif tts_provider == "chatterbox":
                        duration = await generate_audio_chatterbox(
                            text=item.text,
                            voice_id=current_voice_id,
                            output_path=output_path,
                        )
                    else:
                        duration = await generate_audio_elevenlabs(
                            text=item.text,
                            voice_id=current_voice_id,
                            output_path=output_path,
                            client=client,
                            voice_style=voice_style,
                            voice_speed=voice_speed,
                        )
                    segment_has_audio = True
                except Exception as e:
                    error_msg = str(e)
                    text_preview = item.text[:50] + "..." if len(item.text) > 50 else item.text
                    print(f"ERROR generating audio for {segment.type}[{seg_idx}.{item_idx}]: {error_msg}")
                    print(f"  Text: {text_preview}")
                    errors.append(TTSError(
                        segment_type=segment.type,
                        segment_index=seg_idx,
                        item_index=item_idx,
                        text_preview=text_preview,
                        error=error_msg,
                    ))
                    continue

            audio_segments.append(
                AudioSegment(
                    audio_path=output_path,
                    text=item.text,
                    voice_id=current_voice_id,
                    duration_seconds=duration,
                    segment_type=segment.type,
                    item_index=segment_index,
                )
            )
            segment_index += 1

            await asyncio.sleep(0.1)

        if not segment_has_audio and segment.items:
            print(f"WARNING: No audio generated for segment type '{segment.type}'")

    actual_segment_types = {seg.segment_type for seg in audio_segments}

    result = TTSResult(
        segments=audio_segments,
        errors=errors,
        expected_segment_types=expected_segment_types,
        actual_segment_types=actual_segment_types,
    )

    print(f"TTS Generation complete:")
    print(f"  - Generated {len(audio_segments)} audio segments")
    print(f"  - Errors: {len(errors)}")
    print(f"  - Expected types: {expected_segment_types}")
    print(f"  - Actual types: {actual_segment_types}")
    if result.missing_segment_types:
        print(f"  - MISSING types: {result.missing_segment_types}")

    return result


async def list_available_voices() -> list[dict]:
    """List custom ElevenLabs voices configured in settings."""
    settings = get_settings()

    if not settings.elevenlabs_api_key:
        return []

    allowed_voice_ids = set(settings.elevenlabs_custom_voice_ids or [])

    if not allowed_voice_ids:
        return []

    def fetch_voices_sync():
        client = ElevenLabs(api_key=settings.elevenlabs_api_key)
        voices = client.voices.get_all()
        return [
            {
                "voice_id": v.voice_id,
                "name": v.name,
                "labels": v.labels,
                "description": v.description,
            }
            for v in voices.voices
            if v.voice_id in allowed_voice_ids
        ]

    return await asyncio.to_thread(fetch_voices_sync)

