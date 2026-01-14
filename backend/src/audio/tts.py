"""TTS integration with ElevenLabs and Edge TTS support."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import hashlib
import re

from elevenlabs import ElevenLabs

from src.api.schemas import BriefingScript, ScriptSegmentItem
from src.config import get_settings


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
    text_preview: str  # First 50 chars of text
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


# Voice mapping for demographics
# Maps demographic descriptions to ElevenLabs voice IDs
# These are ElevenLabs stock voices - you can customize with your own
VOICE_PROFILES = {
    # Host voices
    "host": "21m00Tcm4TlvDq8ikWAM",  # Rachel - default host

    # American voices
    "male_american": "pNInz6obpgDQGcFmaJgB",  # Adam
    "female_american": "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "male_american_30s": "pNInz6obpgDQGcFmaJgB",  # Adam
    "male_american_40s": "VR6AewLTigWG4xSOukaG",  # Arnold
    "male_american_50s": "VR6AewLTigWG4xSOukaG",  # Arnold
    "female_american_30s": "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "female_american_40s": "21m00Tcm4TlvDq8ikWAM",  # Rachel

    # British voices (using American voices as fallback)
    "male_british": "pNInz6obpgDQGcFmaJgB",  # Adam
    "female_british": "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "male_british_30s": "pNInz6obpgDQGcFmaJgB",  # Adam
    "male_british_40s": "pNInz6obpgDQGcFmaJgB",  # Adam
    "female_british_30s": "21m00Tcm4TlvDq8ikWAM",  # Rachel

    # Older voices
    "male_older": "VR6AewLTigWG4xSOukaG",  # Arnold
    "female_older": "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "male_older_60s": "VR6AewLTigWG4xSOukaG",  # Arnold
    "male_older_70s": "VR6AewLTigWG4xSOukaG",  # Arnold

    # Regional/international (best approximations with stock voices)
    "male_australian": "pNInz6obpgDQGcFmaJgB",  # Adam
    "female_australian": "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "male_irish": "pNInz6obpgDQGcFmaJgB",  # Adam
    "female_irish": "21m00Tcm4TlvDq8ikWAM",  # Rachel

    # Note: For more accurate regional voices, consider:
    # - Using ElevenLabs voice cloning
    # - Adding custom voices via the API
    # - Using voice design feature
}


# Edge TTS voice profiles (Microsoft Edge online TTS)
# Full list: https://github.com/rany2/edge-tts
EDGE_VOICE_PROFILES = {
    # Host voices - natural, professional American voices
    "host": "en-US-GuyNeural",  # Male American - good for radio

    # American voices
    "male_american": "en-US-GuyNeural",
    "female_american": "en-US-JennyNeural",
    "male_american_30s": "en-US-GuyNeural",
    "male_american_40s": "en-US-DavisNeural",
    "male_american_50s": "en-US-DavisNeural",
    "female_american_30s": "en-US-JennyNeural",
    "female_american_40s": "en-US-AriaNeural",

    # British voices
    "male_british": "en-GB-RyanNeural",
    "female_british": "en-GB-SoniaNeural",
    "male_british_30s": "en-GB-RyanNeural",
    "male_british_40s": "en-GB-RyanNeural",
    "female_british_30s": "en-GB-SoniaNeural",

    # Older voices (use deeper/mature sounding voices)
    "male_older": "en-US-DavisNeural",
    "female_older": "en-US-AriaNeural",
    "male_older_60s": "en-US-DavisNeural",
    "male_older_70s": "en-US-DavisNeural",

    # Regional/international
    "male_australian": "en-AU-WilliamNeural",
    "female_australian": "en-AU-NatashaNeural",
    "male_irish": "en-IE-ConnorNeural",
    "female_irish": "en-IE-EmilyNeural",
}

# Default Edge voice for host
DEFAULT_EDGE_VOICE = "en-US-GuyNeural"


# Chatterbox voice profiles (self-hosted TTS)
# Maps voice IDs to Chatterbox API parameters
CHATTERBOX_VOICE_PROFILES = {
    # Host voice - uses voice cloning with custom reference
    "host": {
        "voice_mode": "clone",
        "reference_audio_filename": "TimmyVoice.mp3",
        "display_name": "Timmy",
        "description": "Custom voice clone",
    },
    "timmy": {
        "voice_mode": "clone",
        "reference_audio_filename": "TimmyVoice.mp3",
        "display_name": "Timmy",
        "description": "Custom voice clone",
    },
    # Predefined voices
    "austin": {
        "voice_mode": "predefined",
        "predefined_voice_id": "Austin.wav",
        "display_name": "Austin",
        "description": "Male, American",
    },
    "alice": {
        "voice_mode": "predefined",
        "predefined_voice_id": "Alice.wav",
        "display_name": "Alice",
        "description": "Female, American",
    },
}

# Default Chatterbox voice for host
DEFAULT_CHATTERBOX_VOICE = "timmy"


def match_voice_to_profile(profile: Optional[str], provider: str = "elevenlabs") -> str:
    """Match a demographic profile description to a voice ID.

    Args:
        profile: Demographic description (e.g., "male_american_40s")
        provider: TTS provider ("elevenlabs", "edge", or "chatterbox")

    Returns:
        Voice ID appropriate for the provider
    """
    settings = get_settings()

    # Choose profile dict based on provider
    if provider == "edge":
        profiles = EDGE_VOICE_PROFILES
        default_voice = DEFAULT_EDGE_VOICE
    elif provider == "chatterbox":
        # Chatterbox uses simple voice IDs, not demographic profiles
        # Just return the default voice for non-host voices
        profiles = {"host": DEFAULT_CHATTERBOX_VOICE}
        default_voice = DEFAULT_CHATTERBOX_VOICE
    else:
        profiles = VOICE_PROFILES
        default_voice = settings.elevenlabs_host_voice_id

    if not profile:
        return default_voice

    # Normalize the profile string
    profile_lower = profile.lower().strip()

    # Try exact match first
    if profile_lower in profiles:
        return profiles[profile_lower]

    # For chatterbox, just return default if no exact match
    if provider == "chatterbox":
        return default_voice

    # Try partial matching (for ElevenLabs and Edge)
    best_match = None
    best_score = 0

    for key, voice_id in profiles.items():
        # Count matching words
        key_words = set(key.split("_"))
        profile_words = set(re.split(r"[_\s]+", profile_lower))

        matches = len(key_words & profile_words)
        if matches > best_score:
            best_score = matches
            best_match = voice_id

    if best_match:
        return best_match

    # Default to host voice
    return default_voice


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
    import edge_tts

    # Convert speed to Edge TTS rate format (+/-percentage)
    # 1.0 = normal, 1.1 = +10%, 0.9 = -10%
    if voice_speed != 1.0:
        rate_percent = int((voice_speed - 1.0) * 100)
        rate = f"{rate_percent:+d}%"
    else:
        rate = "+0%"

    # Generate audio
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(output_path))

    # Calculate duration
    from pydub import AudioSegment as PydubSegment
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
    import httpx

    settings = get_settings()

    # Get voice profile configuration
    voice_config = CHATTERBOX_VOICE_PROFILES.get(
        voice_id.lower(),
        CHATTERBOX_VOICE_PROFILES[DEFAULT_CHATTERBOX_VOICE]
    )

    # Build request payload
    # Use split_text with max chunk_size (500) to handle long text while minimizing
    # chunk boundaries that can cause artifacts. Short text won't be split anyway.
    payload = {
        "text": text,
        "voice_mode": voice_config["voice_mode"],
        "output_format": "mp3",
        "split_text": True,
        "chunk_size": 500,  # Max allowed - fewer chunks = fewer potential artifacts
        # Voice generation parameters
        "temperature": 0.7,
        "exaggeration": 0.7,
        "cfg_weight": 0.5,
        "seed": 1986,
    }

    # Add voice-specific parameters
    if voice_config["voice_mode"] == "clone":
        payload["reference_audio_filename"] = voice_config["reference_audio_filename"]
    else:
        payload["predefined_voice_id"] = voice_config["predefined_voice_id"]

    # Determine URL - use dev URL if not running in Docker (check if host.docker.internal resolves)
    chatterbox_url = settings.chatterbox_url

    # Try to call the Chatterbox API
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                f"{chatterbox_url}/tts",
                json=payload,
            )
            response.raise_for_status()
        except httpx.ConnectError:
            # Fall back to dev URL if Docker URL fails
            chatterbox_url = settings.chatterbox_dev_url
            response = await client.post(
                f"{chatterbox_url}/tts",
                json=payload,
            )
            response.raise_for_status()

        # Write audio to file
        with open(output_path, "wb") as f:
            f.write(response.content)

    # Calculate duration
    from pydub import AudioSegment as PydubSegment
    audio = PydubSegment.from_mp3(output_path)
    duration_seconds = len(audio) / 1000.0

    return duration_seconds


async def generate_audio_for_text(
    text: str,
    voice_id: str,
    output_path: Path,
    client: ElevenLabs,
    voice_style: str = "energetic",
    voice_speed: float = 1.1,
) -> float:
    """Generate audio for a single text segment.

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

    # Voice settings based on style
    # Lower stability = more expressive, higher style = more dramatic
    voice_settings = {
        "energetic": {
            "stability": 0.35,  # More expressive
            "similarity_boost": 0.75,
            "style": 0.65,  # More stylized
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

    style_config = voice_settings.get(voice_style, voice_settings["energetic"])

    # Generate audio with voice settings (run in thread to avoid blocking event loop)
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
        # Write to file
        with open(output_path, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)

    await asyncio.to_thread(generate_sync)

    # Calculate duration using pydub
    from pydub import AudioSegment as PydubSegment

    audio = PydubSegment.from_mp3(output_path)

    # Adjust speed if not 1.0
    if voice_speed != 1.0 and 0.5 <= voice_speed <= 2.0:
        # Speed up or slow down
        # speedup = 1.1 means 10% faster
        audio = audio.speedup(playback_speed=voice_speed)
        audio.export(output_path, format="mp3")

    duration_seconds = len(audio) / 1000.0

    return duration_seconds


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

    # Setup based on provider
    client = None
    if tts_provider == "elevenlabs":
        if not settings.elevenlabs_api_key:
            raise ValueError("ELEVENLABS_API_KEY not configured")
        client = ElevenLabs(api_key=settings.elevenlabs_api_key)
        host_voice_id = voice_id or settings.elevenlabs_host_voice_id
    elif tts_provider == "chatterbox":
        # Chatterbox - self-hosted, no API key needed
        host_voice_id = voice_id or DEFAULT_CHATTERBOX_VOICE
    else:
        # Edge TTS - no API key needed
        host_voice_id = EDGE_VOICE_PROFILES.get("host", DEFAULT_EDGE_VOICE)

    # Create temp directory for audio segments
    temp_dir = settings.audio_output_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    audio_segments = []
    errors = []
    segment_index = 0

    # Track expected segment types from script
    expected_segment_types = {seg.type for seg in script.segments if seg.items}

    print(f"Generating audio with provider={tts_provider}, voice_style={voice_style}, voice_speed={voice_speed}")
    print(f"Expected segment types: {expected_segment_types}")

    for seg_idx, segment in enumerate(script.segments):
        segment_has_audio = False

        for item_idx, item in enumerate(segment.items):
            if not item.text.strip():
                continue

            # Determine voice based on provider
            if item.voice == "host":
                current_voice_id = host_voice_id
            else:
                current_voice_id = match_voice_to_profile(item.voice_profile, provider=tts_provider)

            # Generate unique filename based on content hash + voice + style + provider
            # IMPORTANT: voice_id must be included to avoid serving cached audio from wrong voice
            content_key = f"{item.text}{current_voice_id}{voice_style}{voice_speed}{tts_provider}"
            text_hash = hashlib.md5(content_key.encode()).hexdigest()[:8]
            filename = f"seg_{seg_idx:02d}_{item_idx:02d}_{text_hash}.mp3"
            output_path = temp_dir / filename

            # Skip if already generated (caching)
            if output_path.exists():
                from pydub import AudioSegment as PydubSegment
                audio = PydubSegment.from_mp3(output_path)
                duration = len(audio) / 1000.0
                segment_has_audio = True
            else:
                # Generate audio based on provider
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
                        duration = await generate_audio_for_text(
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

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.1)

        if not segment_has_audio and segment.items:
            print(f"WARNING: No audio generated for segment type '{segment.type}'")

    # Determine which segment types actually got audio
    actual_segment_types = {seg.segment_type for seg in audio_segments}

    result = TTSResult(
        segments=audio_segments,
        errors=errors,
        expected_segment_types=expected_segment_types,
        actual_segment_types=actual_segment_types,
    )

    # Log summary
    print(f"TTS Generation complete:")
    print(f"  - Generated {len(audio_segments)} audio segments")
    print(f"  - Errors: {len(errors)}")
    print(f"  - Expected types: {expected_segment_types}")
    print(f"  - Actual types: {actual_segment_types}")
    if result.missing_segment_types:
        print(f"  - MISSING types: {result.missing_segment_types}")

    return result


async def list_available_voices() -> list[dict]:
    """List custom ElevenLabs voices configured in settings.

    Only returns voices that are explicitly allowed in the
    elevenlabs_custom_voice_ids config setting.
    """
    settings = get_settings()

    if not settings.elevenlabs_api_key:
        return []

    # Get the list of allowed custom voice IDs from config
    allowed_voice_ids = set(settings.elevenlabs_custom_voice_ids or [])

    if not allowed_voice_ids:
        return []

    def fetch_voices_sync():
        client = ElevenLabs(api_key=settings.elevenlabs_api_key)
        voices = client.voices.get_all()
        # Only return voices that are in the allowed list
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
