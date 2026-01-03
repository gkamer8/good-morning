"""Application configuration and settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    anthropic_api_key: str = ""
    elevenlabs_api_key: str = ""
    news_api_key: str = ""  # Optional - can use RSS feeds without it
    weather_api_key: str = ""  # Optional - Open-Meteo doesn't require one

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/morning_drive.db"

    # Storage paths
    data_dir: Path = Path("./data")
    assets_dir: Path = Path("./assets")
    audio_output_dir: Path = Path("./data/audio")

    # ElevenLabs settings
    elevenlabs_host_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Default: Rachel
    elevenlabs_model_id: str = "eleven_turbo_v2_5"

    # Custom voices to show in the app (in addition to stock voices)
    # These are voice IDs from your ElevenLabs account that you want to include
    elevenlabs_custom_voice_ids: list[str] = [
        "BG48ZiEunXWfskS4bWOW",  # Firing Line
    ]

    # MinIO settings for music storage
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "morning-drive-music"
    minio_secure: bool = False  # Use HTTP for local development

    # Generation settings
    default_briefing_duration_minutes: int = 10
    max_briefing_duration_minutes: int = 30

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Admin interface
    admin_password: str = "changeme"  # Change this in production via ADMIN_PASSWORD env var

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audio_output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
