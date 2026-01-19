"""TTS data models and result types."""

from dataclasses import dataclass
from pathlib import Path

from src.api.schemas import SegmentType


@dataclass
class AudioSegment:
    """An audio segment with metadata."""

    audio_path: Path
    text: str
    voice_display_name: str
    duration_seconds: float
    segment_type: SegmentType
    item_index: int


@dataclass
class TTSError:
    """Record of a TTS generation error."""

    segment_type: SegmentType
    segment_index: int
    item_index: int
    text_preview: str
    error: str
