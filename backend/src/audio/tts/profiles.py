"""Voice profiles and matching for TTS providers."""

import re
from typing import Optional

from src.config import get_settings


# ElevenLabs voice profiles
VOICE_PROFILES = {
    "host": "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "male_american": "pNInz6obpgDQGcFmaJgB",  # Adam
    "female_american": "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "male_american_30s": "pNInz6obpgDQGcFmaJgB",
    "male_american_40s": "VR6AewLTigWG4xSOukaG",  # Arnold
    "male_american_50s": "VR6AewLTigWG4xSOukaG",
    "female_american_30s": "21m00Tcm4TlvDq8ikWAM",
    "female_american_40s": "21m00Tcm4TlvDq8ikWAM",
    "male_british": "pNInz6obpgDQGcFmaJgB",
    "female_british": "21m00Tcm4TlvDq8ikWAM",
    "male_british_30s": "pNInz6obpgDQGcFmaJgB",
    "male_british_40s": "pNInz6obpgDQGcFmaJgB",
    "female_british_30s": "21m00Tcm4TlvDq8ikWAM",
    "male_older": "VR6AewLTigWG4xSOukaG",
    "female_older": "21m00Tcm4TlvDq8ikWAM",
    "male_older_60s": "VR6AewLTigWG4xSOukaG",
    "male_older_70s": "VR6AewLTigWG4xSOukaG",
    "male_australian": "pNInz6obpgDQGcFmaJgB",
    "female_australian": "21m00Tcm4TlvDq8ikWAM",
    "male_irish": "pNInz6obpgDQGcFmaJgB",
    "female_irish": "21m00Tcm4TlvDq8ikWAM",
}


# Edge TTS voice profiles
EDGE_VOICE_PROFILES = {
    "host": "en-US-GuyNeural",
    "male_american": "en-US-GuyNeural",
    "female_american": "en-US-JennyNeural",
    "male_american_30s": "en-US-GuyNeural",
    "male_american_40s": "en-US-DavisNeural",
    "male_american_50s": "en-US-DavisNeural",
    "female_american_30s": "en-US-JennyNeural",
    "female_american_40s": "en-US-AriaNeural",
    "male_british": "en-GB-RyanNeural",
    "female_british": "en-GB-SoniaNeural",
    "male_british_30s": "en-GB-RyanNeural",
    "male_british_40s": "en-GB-RyanNeural",
    "female_british_30s": "en-GB-SoniaNeural",
    "male_older": "en-US-DavisNeural",
    "female_older": "en-US-AriaNeural",
    "male_older_60s": "en-US-DavisNeural",
    "male_older_70s": "en-US-DavisNeural",
    "male_australian": "en-AU-WilliamNeural",
    "female_australian": "en-AU-NatashaNeural",
    "male_irish": "en-IE-ConnorNeural",
    "female_irish": "en-IE-EmilyNeural",
}

DEFAULT_EDGE_VOICE = "en-US-GuyNeural"


# Chatterbox voice profiles
CHATTERBOX_VOICE_PROFILES = {
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

    if provider == "edge":
        profiles = EDGE_VOICE_PROFILES
        default_voice = DEFAULT_EDGE_VOICE
    elif provider == "chatterbox":
        profiles = {"host": DEFAULT_CHATTERBOX_VOICE}
        default_voice = DEFAULT_CHATTERBOX_VOICE
    else:
        profiles = VOICE_PROFILES
        default_voice = settings.elevenlabs_host_voice_id

    if not profile:
        return default_voice

    profile_lower = profile.lower().strip()

    if profile_lower in profiles:
        return profiles[profile_lower]

    if provider == "chatterbox":
        return default_voice

    # Try partial matching
    best_match = None
    best_score = 0

    for key, voice_id in profiles.items():
        key_words = set(key.split("_"))
        profile_words = set(re.split(r"[_\s]+", profile_lower))

        matches = len(key_words & profile_words)
        if matches > best_score:
            best_score = matches
            best_match = voice_id

    if best_match:
        return best_match

    return default_voice

