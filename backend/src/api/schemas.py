"""Pydantic schemas for API request/response models."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, create_model


# === Utilities ===


def partial_model(model: type[BaseModel], name: str | None = None) -> type[BaseModel]:
    """
    Create a partial (all-optional) version of a Pydantic model.

    Takes a base model and returns a new model where all fields are Optional
    with None defaults. Useful for PUT/PATCH update endpoints that accept
    partial updates.

    Args:
        model: The base Pydantic model to make partial
        name: Optional name for the new model (defaults to {ModelName}Update)

    Returns:
        A new Pydantic model with all fields optional
    """
    fields = {
        field_name: (Optional[field_info.annotation], None)
        for field_name, field_info in model.model_fields.items()
    }
    return create_model(
        name or f"{model.__name__}Update",
        __doc__=f"{model.__name__} with all fields optional for partial updates.",
        **fields,
    )


# === Constants ===

CLAUDE_MODEL = "claude-sonnet-4-20250514"
DEFAULT_WRITING_STYLE = "good_morning_america"
DEFAULT_SEGMENT_ORDER = ["news", "sports", "weather", "fun"]
DEFAULT_VOICE = "host"


# === Enums ===


class BriefingStatus(str, Enum):
    """Status of a briefing generation."""

    PENDING = "pending"
    GATHERING_CONTENT = "gathering_content"
    WRITING_SCRIPT = "writing_script"
    RESEARCHING_STORIES = "researching_stories"
    GENERATING_AUDIO = "generating_audio"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LengthMode(str, Enum):
    """Briefing length mode."""

    SHORT = "short"
    LONG = "long"


class GenerationPhase(str, Enum):
    """Phase during briefing generation (for error tracking)."""

    SETUP = "setup"
    GATHERING_CONTENT = "gathering_content"
    WRITING_SCRIPT = "writing_script"
    RESEARCHING_STORIES = "researching_stories"
    GENERATING_AUDIO = "generating_audio"
    UNKNOWN = "unknown"


class SegmentType(str, Enum):
    """Types of briefing segments."""

    INTRO = "intro"
    NEWS = "news"
    SPORTS = "sports"
    WEATHER = "weather"
    FUN = "fun"
    MUSIC = "music"
    OUTRO = "outro"
    UNKNOWN = "unknown"


# Set of statuses that indicate briefing is still in progress
IN_PROGRESS_STATUSES = {
    BriefingStatus.PENDING,
    BriefingStatus.GATHERING_CONTENT,
    BriefingStatus.WRITING_SCRIPT,
    BriefingStatus.RESEARCHING_STORIES,
    BriefingStatus.GENERATING_AUDIO,
    BriefingStatus.FINALIZING,
}

# Progress percentages and display messages for each status
STATUS_PROGRESS: dict[BriefingStatus, tuple[int, str]] = {
    BriefingStatus.PENDING: (0, "Waiting to start..."),
    BriefingStatus.GATHERING_CONTENT: (2, "Gathering news, sports, and weather..."),
    BriefingStatus.WRITING_SCRIPT: (8, "Writing radio script..."),
    BriefingStatus.RESEARCHING_STORIES: (25, "Researching stories in depth..."),
    BriefingStatus.GENERATING_AUDIO: (50, "Generating audio..."),
    BriefingStatus.FINALIZING: (95, "Finalizing your briefing..."),
    BriefingStatus.COMPLETED: (100, "Complete!"),
    BriefingStatus.COMPLETED_WITH_WARNINGS: (100, "Complete (with warnings)"),
    BriefingStatus.FAILED: (0, "Generation failed"),
    BriefingStatus.CANCELLED: (0, "Cancelled"),
}


# === Content Limits Configuration ===


@dataclass
class ContentLimits:
    """Content limits based on briefing length mode."""

    news_stories_per_source: int  # Stories per news outlet
    history_events: int  # This Day in History events
    finance_movers_limit: Optional[int]  # Gainers/losers each; None = all
    sports_favorite_teams_only: bool  # True = only favorite teams
    target_duration_minutes: int  # Target briefing duration
    target_word_count: int  # Approximate word count


CONTENT_LIMITS: dict[LengthMode, ContentLimits] = {
    LengthMode.SHORT: ContentLimits(
        news_stories_per_source=1,
        history_events=1,
        finance_movers_limit=1,  # 1 gainer + 1 loser
        sports_favorite_teams_only=True,
        target_duration_minutes=5,
        target_word_count=1000,
    ),
    LengthMode.LONG: ContentLimits(
        news_stories_per_source=2,
        history_events=2,
        finance_movers_limit=None,  # All (5 + 5)
        sports_favorite_teams_only=False,
        target_duration_minutes=10,
        target_word_count=2000,
    ),
}


# === Briefing Schemas ===


class BriefingSegment(BaseModel):
    """A segment within a briefing."""

    type: str  # intro, news, sports, weather, fun, music, outro
    start_time: float  # seconds from start
    end_time: float
    title: str


class BriefingBase(BaseModel):
    """Base briefing model."""

    title: str
    duration_seconds: float
    segments: list[BriefingSegment] = []


class BriefingCreate(BaseModel):
    """Request to generate a new briefing."""

    override_length: Optional[str] = Field(
        default=None,
        description="Override briefing length: 'short' or 'long'",
        pattern="^(short|long)$",
    )
    override_topics: Optional[list[str]] = None


class BriefingResponse(BriefingBase):
    """Briefing response with metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    audio_url: str
    status: str


class BriefingListResponse(BaseModel):
    """List of briefings."""

    briefings: list[BriefingResponse]
    total: int


# === Settings Schemas ===


class WeatherLocation(BaseModel):
    """A weather location."""

    name: str
    lat: float
    lon: float


class SportsTeam(BaseModel):
    """A sports team to follow."""

    name: str
    league: str  # nfl, mlb, nhl, atp, pga, etc.
    team_id: Optional[str] = None  # API-specific identifier


class SettingsBase(BaseModel):
    """User settings base model."""

    # News
    news_topics: list[str] = Field(
        default=["top", "technology", "business"],
        description="News categories to include",
    )
    news_sources: list[str] = Field(
        default=["bbc", "npr", "nyt"],
        description="Preferred news sources",
    )

    # Sports
    sports_teams: list[SportsTeam] = Field(default=[])
    sports_leagues: list[str] = Field(
        default=["nfl", "mlb", "nhl"],
        description="Leagues to follow for general updates",
    )

    # Weather
    weather_locations: list[WeatherLocation] = Field(
        default=[WeatherLocation(name="New York", lat=40.7128, lon=-74.0060)]
    )

    # Fun segments
    fun_segments: list[str] = Field(
        default=["this_day_in_history", "market_minute", "quote_of_the_day"],
        description="Fun segment types to include",
    )

    # Preferences
    briefing_length: str = Field(
        default="short",
        description="Briefing length: 'short' (~5 min) or 'long' (~10 min)",
        pattern="^(short|long)$",
    )
    include_intro_music: bool = True
    include_transitions: bool = True

    # News exclusions - free-text topics to filter out from news segment
    news_exclusions: list[str] = Field(
        default=[],
        description="Topics to exclude from news segment (e.g., 'earthquakes outside US', 'celebrity gossip')",
    )

    # Voice settings
    voice_id: str = Field(
        default="timmy",  # Default Chatterbox voice
        description="Voice ID (provider-specific: Chatterbox uses 'timmy', 'austin', 'alice'; ElevenLabs uses their voice IDs)",
    )
    voice_style: str = Field(
        default="energetic",
        description="Voice style: energetic, calm, professional",
    )
    voice_speed: float = Field(
        default=1.1,
        ge=0.5,
        le=2.0,
        description="Voice speed multiplier (1.0 = normal, higher = faster)",
    )

    # TTS Provider
    tts_provider: str = Field(
        default="chatterbox",
        description="TTS provider: 'chatterbox' (self-hosted), 'elevenlabs' (paid), or 'edge' (free, Microsoft)",
    )

    # Segment ordering
    segment_order: list[str] = Field(
        default=["news", "sports", "weather", "fun"],
        description="Order of main content segments (intro/outro are always first/last)",
    )

    # Music feature - play a music piece at the end of the briefing
    include_music: bool = Field(
        default=False,
        description="Include a music piece at the end of the briefing",
    )

    # Writing style - affects the tone and style of the generated script
    writing_style: str = Field(
        default="good_morning_america",
        description="Writing style: good_morning_america (upbeat), firing_line (intellectual wit), ernest_hemingway (terse)",
    )

    # User's timezone for all date/time operations
    timezone: str = Field(
        default="America/New_York",
        description="IANA timezone string (e.g., 'America/New_York', 'America/Los_Angeles', 'Europe/London')",
    )

    # Deep dive feature - enables in-depth coverage of 1-2 stories with web research
    deep_dive_enabled: bool = Field(
        default=False,
        description="Enable deep dive research for 1-2 news stories per briefing",
    )


# SettingsUpdate: All fields from SettingsBase, but Optional for partial updates
SettingsUpdate = partial_model(SettingsBase, "SettingsUpdate")


class SettingsResponse(SettingsBase):
    """Settings response."""

    model_config = ConfigDict(from_attributes=True)

    updated_at: datetime


# === Schedule Schemas ===


class ScheduleBase(BaseModel):
    """Schedule base model."""

    enabled: bool = True
    days_of_week: list[int] = Field(
        default=[0, 1, 2, 3, 4],
        description="Days of week (0=Monday, 6=Sunday)",
    )
    time_hour: int = Field(default=6, ge=0, le=23)
    time_minute: int = Field(default=0, ge=0, le=59)
    timezone: str = "America/New_York"


# ScheduleUpdate: All fields from ScheduleBase, but Optional for partial updates
ScheduleUpdate = partial_model(ScheduleBase, "ScheduleUpdate")


class ScheduleResponse(ScheduleBase):
    """Schedule response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    next_run: Optional[datetime] = None


# === Script Schemas (internal) ===


class ScriptSegmentItem(BaseModel):
    """An item within a script segment."""

    voice: str = "host"  # host, quote
    voice_profile: Optional[str] = None  # For quotes: male_american_40s, etc.
    text: str
    attribution: Optional[str] = None  # For quotes: who said it


class ScriptSegment(BaseModel):
    """A segment in the full script."""

    type: str  # intro, news, sports, weather, fun, music, outro
    items: list[ScriptSegmentItem] = []
    background_music: Optional[str] = None
    transition_in: Optional[str] = None


class BriefingScript(BaseModel):
    """The full briefing script for TTS generation."""

    date: str
    target_duration_minutes: int
    segments: list[ScriptSegment]


# === Generation Status ===


class GenerationError(BaseModel):
    """An error that occurred during generation."""

    phase: str  # gathering_content, writing_script, generating_audio
    component: str  # news, sports, weather, tts, etc.
    message: str
    recoverable: bool = True  # Can continue with fallback?
    fallback_description: Optional[str] = None  # What happens if user continues


class PendingAction(BaseModel):
    """Action waiting for user confirmation."""

    action_id: str  # Unique ID for this action
    error: GenerationError
    options: list[str] = ["continue", "cancel"]  # Available actions


class GenerationStatus(BaseModel):
    """Status of a briefing generation."""

    briefing_id: int
    # Status values:
    # - pending: waiting to start
    # - gathering_content: fetching news/sports/weather
    # - writing_script: Claude generating script
    # - generating_audio: TTS processing
    # - completed: finished successfully
    # - completed_with_warnings: finished but had non-fatal errors
    # - failed: unrecoverable error
    # - cancelled: user cancelled
    status: str
    progress_percent: int = 0
    current_step: Optional[str] = None
    error: Optional[str] = None  # Legacy field for simple errors
    errors: list[GenerationError] = []  # All errors encountered
    pending_action: Optional[PendingAction] = None  # Action awaiting user decision


# === Music Schemas ===


class MusicPieceBase(BaseModel):
    """Base model for music pieces."""

    title: str
    composer: str
    description: Optional[str] = None
    duration_seconds: float
    day_of_year_start: int = Field(default=1, ge=1, le=366)
    day_of_year_end: int = Field(default=366, ge=1, le=366)
    is_active: bool = True


class MusicPieceResponse(MusicPieceBase):
    """Music piece response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    s3_key: str
    file_size_bytes: Optional[int] = None


class MusicPieceListResponse(BaseModel):
    """List of music pieces."""

    pieces: list[MusicPieceResponse]
    total: int


class MusicPieceUpdate(BaseModel):
    """Request to update a music piece."""

    title: Optional[str] = None
    composer: Optional[str] = None
    description: Optional[str] = None
    day_of_year_start: Optional[int] = Field(default=None, ge=1, le=366)
    day_of_year_end: Optional[int] = Field(default=None, ge=1, le=366)
    is_active: Optional[bool] = None
