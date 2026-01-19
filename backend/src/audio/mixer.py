"""Audio mixing and assembly pipeline using pydub/FFmpeg."""

import uuid
from pathlib import Path
from typing import Optional

from pydub import AudioSegment as PydubSegment
from pydub.generators import Sine

from src.api.schemas import SegmentType
from src.audio.tts import AudioSegment
from src.config import get_settings
from src.storage.minio_storage import get_minio_storage


# Audio processing constants
SAMPLE_RATE = 44100
CHANNELS = 2
BIT_DEPTH = 16

# Timing constants (in milliseconds)
INTRO_FADE_IN = 2000
INTRO_FADE_OUT = 1500
OUTRO_FADE_IN = 1000
OUTRO_FADE_OUT = 3000
TRANSITION_DURATION = 500
SEGMENT_GAP = 300  # Gap between spoken segments
SECTION_GAP = 1000  # Gap between major sections (news, sports, etc.)


def create_silence(duration_ms: int) -> PydubSegment:
    """Create a silent audio segment."""
    return PydubSegment.silent(duration=duration_ms)


def normalize_audio(audio: PydubSegment, target_dbfs: float = -20.0) -> PydubSegment:
    """Normalize audio to target dBFS level."""
    change_in_dbfs = target_dbfs - audio.dBFS
    return audio.apply_gain(change_in_dbfs)


def apply_compression(
    audio: PydubSegment,
    threshold: float = -20.0,
    ratio: float = 4.0,
) -> PydubSegment:
    """Apply basic compression to audio.

    Note: pydub doesn't have native compression, so this is a simplified
    implementation using gain adjustment. For production, consider using
    FFmpeg filters directly.
    """
    # Simple compression: reduce loud parts
    if audio.dBFS > threshold:
        reduction = (audio.dBFS - threshold) * (1 - 1 / ratio)
        audio = audio.apply_gain(-reduction)
    return audio


async def assemble_briefing_audio(
    briefing_id: int,
    audio_segments: list[AudioSegment],
    include_intro: bool = True,
    include_transitions: bool = True,
    music_audio_path: Optional[Path] = None,
    temp_dir: Optional[Path] = None,
) -> tuple[str, float, dict]:
    """Assemble all audio segments into a final briefing.

    Args:
        briefing_id: ID of the briefing
        audio_segments: List of AudioSegment objects from TTS
        include_intro: Whether to add intro music
        include_transitions: Whether to add transition sounds
        music_audio_path: Path to music audio file (optional)
        temp_dir: Directory for temp files (managed by caller for cleanup)

    Returns:
        Tuple of (s3_key, duration_seconds, segments_metadata)
    """
    settings = get_settings()

    # Audio assets directory
    audio_assets_dir = settings.assets_dir / "audio"
    print(f"[Mixer] Assets dir: {audio_assets_dir.absolute()}")
    print(f"[Mixer] include_intro={include_intro}, include_transitions={include_transitions}")

    # Start with intro jingle
    intro_path = audio_assets_dir / "intro_jingle.mp3"
    print(f"[Mixer] Intro path: {intro_path}, exists: {intro_path.exists()}")
    if include_intro and intro_path.exists():
        intro = PydubSegment.from_mp3(intro_path)
        intro = intro.fade_in(300).fade_out(200)
        intro = normalize_audio(intro, target_dbfs=-22.0)
        final_audio = intro + create_silence(300)
        print(f"[Mixer] Added intro jingle: {len(intro)}ms")
    else:
        # Start with brief silence
        final_audio = create_silence(500)
        print(f"[Mixer] No intro jingle (include_intro={include_intro}, path_exists={intro_path.exists()})")

    # Load segment-specific stings
    segment_stings: dict[SegmentType, PydubSegment] = {}
    sting_types = [SegmentType.NEWS, SegmentType.SPORTS, SegmentType.WEATHER, SegmentType.FUN]
    for sting_type in sting_types:
        sting_path = audio_assets_dir / f"{sting_type.value}_sting.mp3"
        if sting_path.exists():
            sting = PydubSegment.from_mp3(sting_path)
            sting = normalize_audio(sting, target_dbfs=-23.0)
            segment_stings[sting_type] = sting

    # Load transition sounds
    transition_whoosh = None
    transition_chime = None
    if include_transitions:
        whoosh_path = audio_assets_dir / "transition_whoosh.mp3"
        chime_path = audio_assets_dir / "transition_chime.mp3"
        if whoosh_path.exists():
            transition_whoosh = PydubSegment.from_mp3(whoosh_path)
            transition_whoosh = normalize_audio(transition_whoosh, target_dbfs=-25.0)
        if chime_path.exists():
            transition_chime = PydubSegment.from_mp3(chime_path)
            transition_chime = normalize_audio(transition_chime, target_dbfs=-24.0)

    # Track segment timing for metadata
    segments_metadata = {"segments": []}
    current_time_ms = len(final_audio)
    current_section = None

    for i, segment in enumerate(audio_segments):
        # Load the audio file
        try:
            audio = PydubSegment.from_mp3(segment.audio_path)
        except Exception as e:
            print(f"Error loading audio {segment.audio_path}: {e}")
            continue

        # Normalize speech audio
        audio = normalize_audio(audio, target_dbfs=-18.0)

        # Apply light compression for consistent levels
        audio = apply_compression(audio)

        # Add transition between major sections
        if segment.segment_type != current_section:
            if current_section is not None:  # Not the first section
                # Add section gap
                final_audio += create_silence(SECTION_GAP)
                current_time_ms += SECTION_GAP

                # Add transition whoosh between sections
                if transition_whoosh and include_transitions:
                    final_audio += transition_whoosh
                    current_time_ms += len(transition_whoosh)
                    final_audio += create_silence(200)
                    current_time_ms += 200

            # Record new section start
            section_start_time = current_time_ms / 1000.0
            current_section = segment.segment_type

            # Add segment-specific sting if available
            if segment.segment_type in segment_stings and include_transitions:
                final_audio += segment_stings[segment.segment_type]
                current_time_ms += len(segment_stings[segment.segment_type])
                final_audio += create_silence(300)
                current_time_ms += 300

            segments_metadata["segments"].append({
                "type": segment.segment_type.value,
                "start_time": section_start_time,
                "end_time": 0,  # Will be updated
                "title": segment.segment_type.value.replace("_", " ").title(),
            })

        else:
            # Add gap between segments within same section
            final_audio += create_silence(SEGMENT_GAP)
            current_time_ms += SEGMENT_GAP

        # Add the speech segment
        final_audio += audio
        current_time_ms += len(audio)

        # Update section end time
        if segments_metadata["segments"]:
            segments_metadata["segments"][-1]["end_time"] = current_time_ms / 1000.0

    # Add music if provided (after the music intro narration)
    if music_audio_path and music_audio_path.exists():
        try:
            print(f"[Mixer] Adding music from: {music_audio_path}")
            # Use from_file() to auto-detect format (supports mp3, ogg, wav, etc.)
            music_audio = PydubSegment.from_file(str(music_audio_path))

            # Normalize and add fade effects
            music_audio = normalize_audio(music_audio, target_dbfs=-20.0)
            music_audio = music_audio.fade_in(2000).fade_out(3000)

            # Add a brief gap before the music
            final_audio += create_silence(500)
            current_time_ms += 500

            # Record the start of the music
            music_start_time = current_time_ms / 1000.0

            # Add the music
            final_audio += music_audio
            current_time_ms += len(music_audio)

            # Update the music segment end time to include the music
            for seg in segments_metadata["segments"]:
                if seg["type"] == SegmentType.MUSIC.value:
                    seg["end_time"] = current_time_ms / 1000.0

            print(f"[Mixer] Added music: {len(music_audio)}ms")
            segments_metadata["music_added"] = True
            segments_metadata["music_duration"] = len(music_audio) / 1000.0
        except Exception as e:
            print(f"[Mixer] Error adding music: {e}")
            segments_metadata["music_error"] = str(e)
        # Music temp file cleanup is handled by orchestrator's temp directory
    elif music_audio_path:
        print(f"[Mixer] Music audio file not found: {music_audio_path}")
        segments_metadata["music_error"] = "File not found"

    # Add outro jingle if available
    outro_path = audio_assets_dir / "outro_jingle.mp3"
    if include_intro and outro_path.exists():
        outro = PydubSegment.from_mp3(outro_path)
        outro = outro.fade_in(200).fade_out(500)
        outro = normalize_audio(outro, target_dbfs=-22.0)

        final_audio += create_silence(SECTION_GAP)
        final_audio += outro
    else:
        # End with brief silence
        final_audio += create_silence(1000)

    # Final normalization pass
    final_audio = normalize_audio(final_audio, target_dbfs=-16.0)

    # Calculate final duration
    duration_seconds = len(final_audio) / 1000.0

    # Generate S3 key for the briefing
    s3_key = f"briefings/briefing_{briefing_id}_{uuid.uuid4().hex[:8]}.mp3"

    # Export to temp directory (managed by orchestrator for cleanup)
    if temp_dir:
        temp_path = temp_dir / f"final_briefing_{briefing_id}.mp3"
    else:
        # Fallback for direct calls (e.g., testing) - use a temp file
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        temp_path = Path(temp_file.name)
        temp_file.close()

    # Export final audio to temp file
    final_audio.export(
        temp_path,
        format="mp3",
        bitrate="192k",
        parameters=[
            "-ar", str(SAMPLE_RATE),
            "-ac", str(CHANNELS),
        ],
    )

    # Upload to S3
    storage = get_minio_storage()
    await storage.upload_file(temp_path, s3_key, content_type="audio/mpeg")
    print(f"[Mixer] Uploaded briefing to S3: {s3_key}")

    # Temp file cleanup is handled by orchestrator's temp directory context

    return s3_key, duration_seconds, segments_metadata


async def create_sample_assets():
    """Create placeholder audio assets for testing.

    In production, replace these with actual intro/outro music
    and transition sounds.
    """
    settings = get_settings()
    settings.assets_dir.mkdir(parents=True, exist_ok=True)

    # Create a simple intro tone (placeholder)
    intro_path = settings.assets_dir / "intro.mp3"
    if not intro_path.exists():
        # Generate a simple tone sequence as placeholder
        # Create a pleasant chord progression
        tone1 = Sine(440).to_audio_segment(duration=500).fade_in(100).fade_out(100)
        tone2 = Sine(554).to_audio_segment(duration=500).fade_in(100).fade_out(100)
        tone3 = Sine(659).to_audio_segment(duration=1000).fade_in(100).fade_out(500)

        intro = tone1 + tone2 + tone3
        intro = intro - 10  # Reduce volume
        intro.export(intro_path, format="mp3")

    # Create a simple transition tone
    transition_path = settings.assets_dir / "transition.mp3"
    if not transition_path.exists():
        tone = Sine(880).to_audio_segment(duration=200).fade_in(50).fade_out(100)
        tone = tone - 15  # Reduce volume
        tone.export(transition_path, format="mp3")

    # Create a simple outro
    outro_path = settings.assets_dir / "outro.mp3"
    if not outro_path.exists():
        tone1 = Sine(659).to_audio_segment(duration=500).fade_in(100).fade_out(100)
        tone2 = Sine(554).to_audio_segment(duration=500).fade_in(100).fade_out(100)
        tone3 = Sine(440).to_audio_segment(duration=1500).fade_in(100).fade_out(800)

        outro = tone1 + tone2 + tone3
        outro = outro - 10
        outro.export(outro_path, format="mp3")
