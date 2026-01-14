"""Database models and initialization."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, JSON, DateTime, Float, Integer, String, Text, func, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.config import get_settings


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class User(Base):
    """A registered user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    apple_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    settings: Mapped[Optional["UserSettings"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    briefings: Mapped[list["Briefing"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class InviteCode(Base):
    """An invite code for user registration."""

    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    used_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class Briefing(Base):
    """A generated morning briefing."""

    __tablename__ = "briefings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
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
    # completed, completed_with_warnings, failed, cancelled

    # Error tracking - stores list of GenerationError dicts
    generation_errors: Mapped[dict] = mapped_column(JSON, default=list)
    # Pending action awaiting user decision - stores PendingAction dict or null
    pending_action: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Rendered prompts for debugging/viewing in admin panel
    rendered_prompts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationship back to user
    user: Mapped[Optional["User"]] = relationship(back_populates="briefings")


class UserSettings(Base):
    """User preferences and settings."""

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, unique=True, index=True
    )
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
    briefing_length: Mapped[str] = mapped_column(String(10), default="short")  # "short" (~5 min) or "long" (~10 min)
    include_intro_music: Mapped[bool] = mapped_column(default=True)
    include_transitions: Mapped[bool] = mapped_column(default=True)

    # News exclusions - topics/subjects to avoid in news segment
    news_exclusions: Mapped[dict] = mapped_column(
        JSON, default=list  # e.g. ["earthquakes outside US", "celebrity gossip"]
    )

    # Voice settings
    voice_id: Mapped[str] = mapped_column(String(100), default="timmy")  # Chatterbox voice ID
    voice_style: Mapped[str] = mapped_column(String(50), default="energetic")  # energetic, calm, professional
    voice_speed: Mapped[float] = mapped_column(Float, default=1.1)  # 0.5-2.0, slightly faster for energy

    # TTS Provider: "chatterbox" (self-hosted), "elevenlabs" (paid), or "edge" (free, Microsoft)
    tts_provider: Mapped[str] = mapped_column(String(50), default="chatterbox")

    # Segment ordering - controls the order of content in briefings
    segment_order: Mapped[dict] = mapped_column(
        JSON, default=lambda: ["news", "sports", "weather", "fun"]
    )  # Order of main content segments (intro and outro are always first/last)

    # Music feature - play a music piece at the end of the briefing
    include_music: Mapped[bool] = mapped_column(default=False)

    # Writing style - affects the tone and style of the generated script
    writing_style: Mapped[str] = mapped_column(String(50), default="good_morning_america")

    # User's timezone for all date/time operations (IANA timezone string)
    timezone: Mapped[str] = mapped_column(String(50), default="America/New_York")

    # Deep dive feature - enables 1-2 in-depth news segments with web research
    deep_dive_enabled: Mapped[bool] = mapped_column(default=False)

    # Relationship back to user
    user: Mapped[Optional["User"]] = relationship(back_populates="settings")


class Schedule(Base):
    """Briefing generation schedule."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(default=True)
    days_of_week: Mapped[dict] = mapped_column(
        JSON, default=lambda: [0, 1, 2, 3, 4]  # Monday-Friday
    )
    time_hour: Mapped[int] = mapped_column(Integer, default=6)  # 6 AM
    time_minute: Mapped[int] = mapped_column(Integer, default=0)
    timezone: Mapped[str] = mapped_column(String(50), default="America/New_York")

    # Relationship back to user
    user: Mapped[Optional["User"]] = relationship(back_populates="schedules")


class AdminSettings(Base):
    """Global admin settings (key-value store)."""

    __tablename__ = "admin_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


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
    # Define expected columns for each table with their SQLite types and defaults
    expected_columns = {
        "user_settings": {
            "user_id": ("INTEGER", "NULL"),  # FK to users table
            "news_exclusions": ("TEXT", "[]"),  # JSON stored as TEXT in SQLite
            "voice_id": ("VARCHAR(100)", "'pNInz6obpgDQGcFmaJgB'"),
            "voice_style": ("VARCHAR(50)", "'energetic'"),
            "voice_speed": ("FLOAT", "1.1"),
            "segment_order": ("TEXT", "'[\"news\", \"sports\", \"weather\", \"fun\"]'"),
            "include_music": ("BOOLEAN", "0"),
            "tts_provider": ("VARCHAR(50)", "'elevenlabs'"),
            "writing_style": ("VARCHAR(50)", "'good_morning_america'"),
            "briefing_length": ("VARCHAR(10)", "'short'"),  # "short" or "long"
            "timezone": ("VARCHAR(50)", "'America/New_York'"),  # IANA timezone string
            "deep_dive_enabled": ("BOOLEAN", "0"),  # Enable deep dive research for news
        },
        "briefings": {
            "user_id": ("INTEGER", "NULL"),  # FK to users table
            "generation_errors": ("TEXT", "'[]'"),  # JSON list of errors
            "pending_action": ("TEXT", "NULL"),  # JSON pending action or null
            "rendered_prompts": ("TEXT", "NULL"),  # JSON rendered prompts for admin viewing
        },
        "schedules": {
            "user_id": ("INTEGER", "NULL"),  # FK to users table
        },
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

        # Migrate duration_minutes to briefing_length if duration_minutes column exists
        # IMPORTANT: Only update NULL values to avoid overwriting user's manual changes
        result = await conn.execute(text("PRAGMA table_info(user_settings)"))
        columns = {row[1] for row in result.fetchall()}
        if "duration_minutes" in columns and "briefing_length" in columns:
            # Check if any rows need migration (briefing_length is NULL)
            check_result = await conn.execute(text(
                "SELECT COUNT(*) FROM user_settings WHERE briefing_length IS NULL"
            ))
            null_count = check_result.scalar()
            if null_count and null_count > 0:
                print(f"[Migration] Converting duration_minutes to briefing_length for {null_count} rows")
                # <= 7 minutes -> "short", > 7 minutes -> "long"
                await conn.execute(text("""
                    UPDATE user_settings
                    SET briefing_length = CASE
                        WHEN duration_minutes <= 7 THEN 'short'
                        ELSE 'long'
                    END
                    WHERE briefing_length IS NULL
                """))

        # Migrate timezone from Schedule to UserSettings if Schedule has non-default timezone
        if "timezone" in columns:
            try:
                result = await conn.execute(text(
                    "SELECT timezone FROM schedules WHERE timezone != 'America/New_York' LIMIT 1"
                ))
                schedule_tz = result.scalar()
                if schedule_tz:
                    print(f"[Migration] Copying timezone '{schedule_tz}' from Schedule to UserSettings")
                    await conn.execute(text(
                        "UPDATE user_settings SET timezone = :tz WHERE timezone = 'America/New_York'"
                    ), {"tz": schedule_tz})
            except Exception as e:
                print(f"[Migration] Error migrating timezone: {e}")


async def init_db():
    """Initialize the database, creating tables if needed."""
    # First, create any new tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Then run migrations to add missing columns to existing tables
    await migrate_db()

    # Note: Settings and schedules are now created per-user during registration.
    # No default global records are created.


async def get_session() -> AsyncSession:
    """Get a database session."""
    async with async_session() as session:
        yield session
