"""TTS integration with Edge TTS and Chatterbox support."""

import os
import shutil
from pathlib import Path

from pydub import audio_segment

from src.api.schemas import BriefingScript
from src.briefing.generation_errors import BriefingId, catch_async_generation_errors

from .models import AudioSegment, SegmentType, TTSError
from .providers import (
    generate_audio_chatterbox,
    generate_audio_edge_tts,
)
from .voice import (
    ChatterboxCloneVoice,
    ChatterboxPredefinedVoice,
    EdgeVoice,
    TTSProvider,
    Voice,
    VOICES,
)

# Path to silent audio file used as fallback when TTS fails
SILENT_AUDIO_PATH = Path(__file__).parent.parent.parent.parent / "assets" / "audio" / "silent_10ms.mp3"
SILENT_AUDIO_DURATION = 0.052  # ~52ms (MP3 minimum frame size)


def _fallback_copy_silent_audio(_text, _voice, output_path: Path) -> float:
    """Copy silent audio to output_path and return its duration."""
    shutil.copy(SILENT_AUDIO_PATH, output_path)
    return SILENT_AUDIO_DURATION


__all__ = [
    "AudioSegment",
    "TTSError",
    "TTSProvider",
    "Voice",
    "EdgeVoice",
    "ChatterboxCloneVoice",
    "ChatterboxPredefinedVoice",
    "VOICES",
    "generate_audio_for_script",
]


@catch_async_generation_errors(
    fallback_fn=_fallback_copy_silent_audio
)
async def generate_audio_for_segment(
    _,  # Unused briefing ID
    text: str,
    voice: Voice,
    output_path: Path
) -> float:
    """
    Places the output audio in output_path and returns the duration
    """
    if voice.provider == TTSProvider.EDGE:
        duration = await generate_audio_edge_tts(
            text=text,
            voice=voice,
            output_path=output_path,
        )
    elif voice.provider == TTSProvider.CHATTERBOX:
        duration = await generate_audio_chatterbox(
            text=text,
            voice=voice,
            output_path=output_path,
        )
    else:
        # If this is not unreachable, the code is wrong.
        raise ValueError(f"Unknown provider: {voice.provider}")
    
    return duration


@catch_async_generation_errors(
    fallback_fn=None  # Not recoverable
)
async def generate_audio_for_script(
    briefing_id: BriefingId,
    script: BriefingScript,
    voice: Voice,
    output_dir: Path,
) -> list[audio_segment]:
    """Generate audio for all segments in a script.

    Args:
        script: The briefing script to generate audio for
        voice: Voice configuration object (introspected HERE for provider selection)
        output_dir: Directory to write audio files to (managed by caller)

    Returns:
        TTSResult with audio segments, any errors, and validation info
    """
    # Go through each segment and generate audio
    audio_segments: list[AudioSegment] = []
    for seg_idx, segment in enumerate(script.segments):
        for item_idx, item in enumerate(segment.items):
            filename = os.path.join(output_dir, f"seg_{item_idx:02d}.mp3")
            duration = await generate_audio_for_segment(briefing_id, item.text, voice=voice, output_path=filename)
            audio_segments.append(
                AudioSegment(
                    audio_path=filename,
                    text=item.text,
                    voice_display_name=voice.display_name,
                    duration_seconds=duration,
                    segment_type=segment.type,
                    item_index=seg_idx,
                )
            )
    return audio_segments
