#!/usr/bin/env python3
"""Initialize music pieces in MinIO and database.

This script downloads public domain classical music from the Internet Archive
and uploads them to MinIO, creating corresponding database records.

Run this script after starting the Docker services:
    python scripts/init_music.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from sqlalchemy import select

from src.config import get_settings
from src.storage.database import MusicPiece, async_session, init_db
from src.storage.minio_storage import get_minio_storage


# Initial music pieces to load
# Using public domain recordings from Internet Archive
# Add more pieces via the admin interface at /admin/music
INITIAL_MUSIC_PIECES = [
    {
        "title": "Moonlight Sonata (1st Movement)",
        "composer": "Ludwig van Beethoven",
        "description": "Beethoven dedicated this piece to his student Countess Giulietta Guicciardi. The 'Moonlight' nickname came from a critic's comparison to moonlight on Lake Lucerne. Beethoven himself wasn't fond of the piece, preferring his other sonatas.",
        "duration_seconds": 360,  # ~6 minutes
        "audio_url": "https://archive.org/download/MoonlightSonata_755/Beethoven-MoonlightSonata.mp3",
        "s3_key": "music/beethoven/moonlight_sonata.mp3",
        "day_of_year_start": 1,
        "day_of_year_end": 366,
    },
]


async def download_audio(url: str, max_retries: int = 3) -> bytes:
    """Download audio from URL with retry logic."""
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                print(f"  Downloading from {url}...")
                response = await client.get(
                    url,
                    follow_redirects=True,
                    headers={"User-Agent": "MorningDrive/1.0 (Music Init Script)"}
                )

                if response.status_code == 503:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)
                        print(f"  Server temporarily unavailable (503), retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise Exception(f"Server unavailable after {max_retries} attempts")

                response.raise_for_status()

                if len(response.content) < 10000:
                    raise Exception(f"Downloaded file too small ({len(response.content)} bytes)")

                print(f"  Downloaded {len(response.content)} bytes")
                return response.content

        except httpx.HTTPError as e:
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                print(f"  Download error: {e}, retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                raise

    raise Exception(f"Failed to download after {max_retries} attempts")


async def piece_exists(s3_key: str) -> bool:
    """Check if a piece already exists in the database."""
    async with async_session() as session:
        result = await session.execute(
            select(MusicPiece).where(MusicPiece.s3_key == s3_key)
        )
        return result.scalar_one_or_none() is not None


async def init_music_pieces():
    """Initialize music pieces in MinIO and database."""
    print("=" * 60)
    print("Morning Drive - Music Initialization Script")
    print("=" * 60)

    # Initialize database
    print("\n[1/3] Initializing database...")
    await init_db()
    print("  Database initialized.")

    # Initialize MinIO
    print("\n[2/3] Initializing MinIO storage...")
    storage = get_minio_storage()
    await storage.ensure_bucket_exists()
    print("  MinIO bucket ready.")

    # Process each piece
    print("\n[3/3] Processing music pieces...")

    for i, piece_data in enumerate(INITIAL_MUSIC_PIECES, 1):
        print(f"\n--- Piece {i}/{len(INITIAL_MUSIC_PIECES)}: {piece_data['title']} by {piece_data['composer']}")

        # Check if already exists
        if await piece_exists(piece_data["s3_key"]):
            print("  Already exists in database, skipping.")
            continue

        # Download audio
        try:
            audio_content = await download_audio(piece_data["audio_url"])
        except Exception as e:
            print(f"  ERROR downloading: {e}")
            continue

        # Upload to MinIO
        try:
            print(f"  Uploading to MinIO ({piece_data['s3_key']})...")
            result = await storage.upload_bytes(
                audio_content,
                piece_data["s3_key"],
                content_type="audio/mpeg"
            )
            print(f"  Uploaded {result['size_bytes']} bytes")
        except Exception as e:
            print(f"  ERROR uploading to MinIO: {e}")
            continue

        # Create database record
        try:
            async with async_session() as session:
                music_piece = MusicPiece(
                    title=piece_data["title"],
                    composer=piece_data["composer"],
                    description=piece_data["description"],
                    s3_key=piece_data["s3_key"],
                    duration_seconds=piece_data["duration_seconds"],
                    file_size_bytes=result["size_bytes"],
                    day_of_year_start=piece_data["day_of_year_start"],
                    day_of_year_end=piece_data["day_of_year_end"],
                    is_active=True,
                )
                session.add(music_piece)
                await session.commit()
                print(f"  Created database record (ID: {music_piece.id})")
        except Exception as e:
            print(f"  ERROR creating database record: {e}")
            continue

    # Summary
    print("\n" + "=" * 60)
    print("Initialization complete!")

    async with async_session() as session:
        result = await session.execute(select(MusicPiece).where(MusicPiece.is_active == True))
        pieces = result.scalars().all()
        print(f"Total active music pieces: {len(pieces)}")
        for p in pieces:
            print(f"  - {p.title} by {p.composer} ({p.duration_seconds}s)")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(init_music_pieces())
