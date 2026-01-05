"""Database models and initialization."""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.config import get_settings


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Briefing(Base):
    """A generated morning briefing."""

    __tablename__ = "briefings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    audio_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    script: Mapped[dict] = mapped_column(JSON, nullable=False)  # Full script JSON
    segments_metadata: Mapped[dict] = mapped_column(JSON, nullable=False)  # Segment timestamps
    status: Mapped[str] = mapped_column(
        String(50), default="completed", nullable=False
    )  # pending, gathering_content, writing_script, generating_audio,
    # awaiting_confirmation, completed, completed_with_warnings, failed, cancelled

    # Error tracking - stores list of GenerationError dicts
    generation_errors: Mapped[dict] = mapped_column(JSON, default=list)
    # Pending action awaiting user decision - stores PendingAction dict or null
    pending_action: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class UserSettings(Base):
    """User preferences and settings."""

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Content preferences
    news_topics: Mapped[dict] = mapped_column(
        JSON, default=lambda: ["technology", "business", "world"]
    )
    news_sources: Mapped[dict] = mapped_column(
        JSON, default=lambda: ["bbc", "npr", "nyt"]
    )

    # Sports
    sports_teams: Mapped[dict] = mapped_column(JSON, default=list)
    sports_leagues: Mapped[dict] = mapped_column(
        JSON, default=lambda: ["nfl", "mlb", "nhl"]
    )

    # Weather
    weather_locations: Mapped[dict] = mapped_column(
        JSON, default=lambda: [{"name": "New York", "lat": 40.7128, "lon": -74.0060}]
    )

    # Fun segments
    fun_segments: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: [
            "this_day_in_history",
            "market_minute",
            "quote_of_the_day",
        ],
    )

    # Briefing preferences
    duration_minutes: Mapped[int] = mapped_column(Integer, default=10)
    include_intro_music: Mapped[bool] = mapped_column(default=True)
    include_transitions: Mapped[bool] = mapped_column(default=True)

    # News exclusions - topics/subjects to avoid
    news_exclusions: Mapped[dict] = mapped_column(
        JSON, default=list  # e.g. ["earthquakes outside US", "celebrity gossip"]
    )

    # Priority topics - topics to emphasize
    priority_topics: Mapped[dict] = mapped_column(
        JSON, default=list  # e.g. ["tech startups", "AI news"]
    )

    # Voice settings
    voice_id: Mapped[str] = mapped_column(String(100), default="pNInz6obpgDQGcFmaJgB")  # Adam - ElevenLabs voice ID
    voice_style: Mapped[str] = mapped_column(String(50), default="energetic")  # energetic, calm, professional
    voice_speed: Mapped[float] = mapped_column(Float, default=1.1)  # 0.5-2.0, slightly faster for energy

    # TTS Provider: "elevenlabs" (paid, high quality) or "edge" (free, Microsoft Edge TTS)
    tts_provider: Mapped[str] = mapped_column(String(50), default="elevenlabs")

    # Segment ordering - controls the order of content in briefings
    segment_order: Mapped[dict] = mapped_column(
        JSON, default=lambda: ["news", "sports", "weather", "fun"]
    )  # Order of main content segments (intro and outro are always first/last)

    # Music feature - play a music piece at the end of the briefing
    include_music: Mapped[bool] = mapped_column(default=False)

    # Writing style - affects the tone and style of the generated script
    writing_style: Mapped[str] = mapped_column(String(50), default="good_morning_america")


class Schedule(Base):
    """Briefing generation schedule."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    days_of_week: Mapped[dict] = mapped_column(
        JSON, default=lambda: [0, 1, 2, 3, 4]  # Monday-Friday
    )
    time_hour: Mapped[int] = mapped_column(Integer, default=6)  # 6 AM
    time_minute: Mapped[int] = mapped_column(Integer, default=0)
    timezone: Mapped[str] = mapped_column(String(50), default="America/New_York")


class MusicPiece(Base):
    """A music piece stored in MinIO for briefing endings."""

    __tablename__ = "music_pieces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Basic info
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    composer: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)  # Fun facts for narration

    # Storage
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)  # Path in MinIO bucket
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=True)

    # Selection criteria - day of year range for when this piece can be selected
    # e.g., play Vivaldi's Spring in spring months
    day_of_year_start: Mapped[int] = mapped_column(Integer, default=1)  # 1-366
    day_of_year_end: Mapped[int] = mapped_column(Integer, default=366)  # 1-366

    # Status
    is_active: Mapped[bool] = mapped_column(default=True)  # Can be selected for briefings


# Database engine and session
settings = get_settings()
engine = create_async_engine(settings.database_url, echo=settings.debug)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def migrate_db():
    """Run database migrations to add any missing columns."""
    from sqlalchemy import text, inspect

    # Define expected columns for each table with their SQLite types and defaults
    expected_columns = {
        "user_settings": {
            "news_exclusions": ("TEXT", "[]"),  # JSON stored as TEXT in SQLite
            "priority_topics": ("TEXT", "[]"),
            "voice_id": ("VARCHAR(100)", "'pNInz6obpgDQGcFmaJgB'"),
            "voice_style": ("VARCHAR(50)", "'energetic'"),
            "voice_speed": ("FLOAT", "1.1"),
            "segment_order": ("TEXT", "'[\"news\", \"sports\", \"weather\", \"fun\"]'"),
            "include_music": ("BOOLEAN", "0"),
            "tts_provider": ("VARCHAR(50)", "'elevenlabs'"),
            "writing_style": ("VARCHAR(50)", "'good_morning_america'"),
        },
        "briefings": {
            "generation_errors": ("TEXT", "'[]'"),  # JSON list of errors
            "pending_action": ("TEXT", "NULL"),  # JSON pending action or null
        },
        "schedules": {},
    }

    async with engine.begin() as conn:
        # Get existing columns for each table
        for table_name, columns in expected_columns.items():
            if not columns:
                continue

            # Get current columns in the table
            result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
            existing_columns = {row[1] for row in result.fetchall()}

            # Add missing columns
            for col_name, (col_type, default_value) in columns.items():
                if col_name not in existing_columns:
                    print(f"[Migration] Adding column {col_name} to {table_name}")
                    try:
                        await conn.execute(
                            text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type} DEFAULT {default_value}")
                        )
                    except Exception as e:
                        print(f"[Migration] Error adding column {col_name}: {e}")


async def init_db():
    """Initialize the database, creating tables if needed."""
    # First, create any new tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Then run migrations to add missing columns to existing tables
    await migrate_db()

    # Create default settings if not exists
    async with async_session() as session:
        result = await session.execute(
            UserSettings.__table__.select().limit(1)
        )
        if not result.first():
            session.add(UserSettings())
            await session.commit()

        result = await session.execute(
            Schedule.__table__.select().limit(1)
        )
        if not result.first():
            session.add(Schedule())
            await session.commit()


async def get_session() -> AsyncSession:
    """Get a database session."""
    async with async_session() as session:
        yield session
