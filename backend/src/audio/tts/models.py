"""TTS data models and result types."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AudioSegment:
    """An audio segment with metadata."""

    audio_path: Path
    text: str
    voice_id: str
    duration_seconds: float
    segment_type: str
    item_index: int


@dataclass
class TTSError:
    """Record of a TTS generation error."""

    segment_type: str
    segment_index: int
    item_index: int
    text_preview: str
    error: str


@dataclass
class TTSResult:
    """Result of TTS generation including any errors."""

    segments: list[AudioSegment]
    errors: list[TTSError]
    expected_segment_types: set[str]
    actual_segment_types: set[str]

    @property
    def missing_segment_types(self) -> set[str]:
        """Return segment types that were expected but not generated."""
        return self.expected_segment_types - self.actual_segment_types

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def is_complete(self) -> bool:
        """Return True if all expected segment types are present."""
        return len(self.missing_segment_types) == 0

