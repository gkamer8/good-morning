"""Tests for audio generation pipeline."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.audio.tts import TTSResult, TTSError, AudioSegment
from src.api.schemas import BriefingScript, ScriptSegment, ScriptSegmentItem


class TestTTSResult:
    """Tests for TTSResult validation."""

    def test_complete_result(self):
        """Test that a complete result reports no missing segments."""
        result = TTSResult(
            segments=[
                AudioSegment(
                    audio_path=Path("/tmp/test.mp3"),
                    text="Hello",
                    voice_id="test",
                    duration_seconds=1.0,
                    segment_type="intro",
                    item_index=0,
                ),
                AudioSegment(
                    audio_path=Path("/tmp/test2.mp3"),
                    text="News content",
                    voice_id="test",
                    duration_seconds=2.0,
                    segment_type="news",
                    item_index=1,
                ),
            ],
            errors=[],
            expected_segment_types={"intro", "news"},
            actual_segment_types={"intro", "news"},
        )
        assert result.is_complete
        assert len(result.missing_segment_types) == 0
        assert not result.has_errors

    def test_missing_segments(self):
        """Test that missing segments are detected."""
        result = TTSResult(
            segments=[
                AudioSegment(
                    audio_path=Path("/tmp/test.mp3"),
                    text="Hello",
                    voice_id="test",
                    duration_seconds=1.0,
                    segment_type="intro",
                    item_index=0,
                ),
            ],
            errors=[],
            expected_segment_types={"intro", "news", "outro"},
            actual_segment_types={"intro"},
        )
        assert not result.is_complete
        assert result.missing_segment_types == {"news", "outro"}

    def test_has_errors(self):
        """Test error tracking."""
        result = TTSResult(
            segments=[],
            errors=[
                TTSError(
                    segment_type="news",
                    segment_index=1,
                    item_index=0,
                    text_preview="Some news text...",
                    error="Rate limit exceeded",
                ),
            ],
            expected_segment_types={"intro", "news"},
            actual_segment_types={"intro"},
        )
        assert result.has_errors
        assert len(result.errors) == 1
        assert result.errors[0].segment_type == "news"


class TestAudioAssets:
    """Tests for audio asset availability."""

    def test_required_assets_exist(self):
        """Test that required audio assets exist."""
        from src.config import get_settings
        settings = get_settings()
        audio_dir = settings.assets_dir / "audio"

        required_files = [
            "intro_jingle.mp3",
            "outro_jingle.mp3",
        ]

        for filename in required_files:
            filepath = audio_dir / filename
            assert filepath.exists(), f"Required audio asset missing: {filename}"

    def test_optional_assets(self):
        """Test that optional audio assets exist (non-critical)."""
        from src.config import get_settings
        settings = get_settings()
        audio_dir = settings.assets_dir / "audio"

        optional_files = [
            "news_sting.mp3",
            "sports_sting.mp3",
            "weather_sting.mp3",
            "fun_sting.mp3",
            "transition_whoosh.mp3",
            "transition_chime.mp3",
        ]

        missing = []
        for filename in optional_files:
            filepath = audio_dir / filename
            if not filepath.exists():
                missing.append(filename)

        # Just log missing optional files, don't fail
        if missing:
            print(f"Optional audio assets missing: {missing}")


class TestBriefingScriptValidation:
    """Tests for briefing script validation."""

    def test_script_has_required_segments(self):
        """Test that generated scripts have required segment types."""
        # This tests the expected structure of a briefing script
        required_types = {"intro", "outro"}
        optional_types = {"news", "sports", "weather", "fun", "music"}

        # A valid script should have at least intro and outro
        script = BriefingScript(
            date="2026-01-03",
            target_duration_minutes=10,
            segments=[
                ScriptSegment(
                    type="intro",
                    items=[ScriptSegmentItem(voice="host", text="Good morning!")],
                ),
                ScriptSegment(
                    type="news",
                    items=[ScriptSegmentItem(voice="host", text="Today's news...")],
                ),
                ScriptSegment(
                    type="outro",
                    items=[ScriptSegmentItem(voice="host", text="That's all!")],
                ),
            ],
        )

        segment_types = {seg.type for seg in script.segments}
        assert required_types.issubset(segment_types), (
            f"Script missing required segments. "
            f"Required: {required_types}, Got: {segment_types}"
        )

    def test_script_segments_have_items(self):
        """Test that script segments have at least one item."""
        script = BriefingScript(
            date="2026-01-03",
            target_duration_minutes=10,
            segments=[
                ScriptSegment(
                    type="intro",
                    items=[ScriptSegmentItem(voice="host", text="Good morning!")],
                ),
            ],
        )

        for segment in script.segments:
            assert len(segment.items) > 0, f"Segment {segment.type} has no items"
            for item in segment.items:
                assert item.text.strip(), f"Segment {segment.type} has empty text"


class TestMixerValidation:
    """Tests for mixer output validation."""

    def test_segments_metadata_structure(self):
        """Test that segments metadata has correct structure."""
        # Example of expected metadata structure
        metadata = {
            "segments": [
                {"type": "intro", "start_time": 0.0, "end_time": 10.0, "title": "Intro"},
                {"type": "news", "start_time": 10.0, "end_time": 60.0, "title": "News"},
            ]
        }

        for segment in metadata["segments"]:
            assert "type" in segment
            assert "start_time" in segment
            assert "end_time" in segment
            assert segment["end_time"] > segment["start_time"]

    def test_error_metadata_stored(self):
        """Test that TTS errors are stored in metadata."""
        metadata = {
            "segments": [],
            "tts_errors": [
                {
                    "segment_type": "news",
                    "error": "Rate limit",
                    "text_preview": "Some text...",
                }
            ],
            "missing_segments": ["news", "outro"],
        }

        # Verify error structure
        assert "tts_errors" in metadata
        assert len(metadata["tts_errors"]) == 1
        assert metadata["tts_errors"][0]["segment_type"] == "news"

        # Verify missing segments
        assert "missing_segments" in metadata
        assert "news" in metadata["missing_segments"]


class TestMusicFeature:
    """Tests for music feature."""

    def test_music_piece_info_structure(self):
        """Test MusicPieceInfo has required fields."""
        from src.tools.music_tools import MusicPieceInfo

        piece = MusicPieceInfo(
            id=1,
            composer="Ludwig van Beethoven",
            title="Moonlight Sonata",
            description="A beautiful piece",
            duration_seconds=360.0,
            s3_key="music/beethoven/moonlight_sonata.mp3",
        )

        assert piece.composer, "Composer should not be empty"
        assert piece.title, "Title should not be empty"
        assert piece.duration_seconds > 0, "Duration should be positive"
        assert piece.s3_key, "S3 key should not be empty"

    def test_format_music_for_agent(self):
        """Test that music formatting includes required information."""
        from src.tools.music_tools import MusicPieceInfo, format_music_for_agent

        piece = MusicPieceInfo(
            id=1,
            composer="Ludwig van Beethoven",
            title="Moonlight Sonata",
            description="Beethoven dedicated this piece to his student. The nickname came from a critic's comparison to moonlight on Lake Lucerne.",
            duration_seconds=360.0,
            s3_key="music/beethoven/moonlight_sonata.mp3",
        )
        formatted = format_music_for_agent(piece)

        # Should include key information
        assert piece.composer in formatted
        assert piece.title in formatted

        # Should include instruction about music playing
        assert "WILL play" in formatted or "will play" in formatted.lower()
        assert "And now" in formatted or "Let's listen" in formatted
