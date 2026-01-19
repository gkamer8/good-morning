"""
Voice type definitions for TTS providers.

The Voice type is a discriminated union that represents a complete voice configuration.
It is only introspected in exactly two places:
1. To determine which TTS provider to use (by checking the `provider` field)
2. To extract provider-specific API parameters (in the provider functions)

NO DEFAULTS. NO FALLBACKS.
"""

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class TTSProvider(str, Enum):
    """TTS provider enum."""

    EDGE = "edge"
    CHATTERBOX = "chatterbox"


class EdgeVoice(BaseModel):
    """Edge TTS voice configuration."""

    provider: Literal[TTSProvider.EDGE] = TTSProvider.EDGE
    voice_name: str  # e.g., "en-US-GuyNeural"
    display_name: str


class ChatterboxCloneVoice(BaseModel):
    """Chatterbox voice clone configuration."""

    provider: Literal[TTSProvider.CHATTERBOX] = TTSProvider.CHATTERBOX
    mode: Literal["clone"] = "clone"
    reference_audio_filename: str  # e.g., "TimmyVoice.mp3"
    display_name: str
    description: str


class ChatterboxPredefinedVoice(BaseModel):
    """Chatterbox predefined voice configuration."""

    provider: Literal[TTSProvider.CHATTERBOX] = TTSProvider.CHATTERBOX
    mode: Literal["predefined"] = "predefined"
    predefined_voice_id: str  # e.g., "Austin.wav"
    display_name: str
    description: str


# Discriminated union for all voice types
Voice = Annotated[
    Union[EdgeVoice, ChatterboxCloneVoice, ChatterboxPredefinedVoice],
    Field(discriminator="provider"),
]


# ============================================================================
# All available voices (canonical definitions)
# ============================================================================

VOICES: dict[str, Voice] = {
    # Chatterbox voices
    "chatterbox_timmy": ChatterboxCloneVoice(
        reference_audio_filename="TimmyVoice.mp3",
        display_name="Timmy",
        description="Custom voice clone",
    ),
    "chatterbox_austin": ChatterboxPredefinedVoice(
        predefined_voice_id="Austin.wav",
        display_name="Austin",
        description="Male, American",
    ),
    "chatterbox_alice": ChatterboxPredefinedVoice(
        predefined_voice_id="Alice.wav",
        display_name="Alice",
        description="Female, American",
    ),
    # Edge TTS voices
    "edge_guy": EdgeVoice(
        voice_name="en-US-GuyNeural",
        display_name="Guy",
    ),
}
