#!/usr/bin/env python3
"""Add new classical music pieces to MinIO and database.

This script downloads public domain classical music recordings from Wikimedia Commons
and uploads them to MinIO storage with corresponding database entries.

These are all public domain recordings from Wikimedia Commons.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from sqlalchemy import select
from pydub import AudioSegment
import io

from src.config import get_settings
from src.storage.database import MusicPiece, async_session, init_db
from src.storage.minio_storage import get_minio_storage


def get_audio_duration(audio_bytes: bytes, format: str = "ogg") -> float:
    """Extract duration in seconds from audio file bytes."""
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=format)
    return len(audio) / 1000.0  # pydub returns milliseconds


async def get_existing_pieces() -> list[dict]:
    """Get list of existing music pieces from database."""
    async with async_session() as session:
        result = await session.execute(select(MusicPiece))
        pieces = result.scalars().all()
        return [
            {
                "id": p.id,
                "title": p.title,
                "composer": p.composer,
                "s3_key": p.s3_key,
            }
            for p in pieces
        ]


async def download_audio(url: str, max_retries: int = 3) -> bytes:
    """Download audio from URL with retry logic."""
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                print(f"  Downloading from {url[:80]}...")
                response = await client.get(
                    url,
                    follow_redirects=True,
                    headers={"User-Agent": "MorningDrive/1.0 (Classical Music Downloader)"}
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


async def piece_exists_by_key(s3_key: str) -> bool:
    """Check if a piece already exists by s3_key."""
    async with async_session() as session:
        result = await session.execute(
            select(MusicPiece).where(MusicPiece.s3_key == s3_key)
        )
        return result.scalar_one_or_none() is not None


async def add_music_piece(piece_data: dict) -> bool:
    """Add a single music piece to MinIO and database."""
    print(f"\n--- Adding: {piece_data['title']} by {piece_data['composer']}")

    # Check if already exists
    if await piece_exists_by_key(piece_data["s3_key"]):
        print("  Already exists in database, skipping.")
        return False

    # Download audio
    try:
        audio_content = await download_audio(piece_data["audio_url"])
    except Exception as e:
        print(f"  ERROR downloading: {e}")
        return False

    # Get audio duration
    audio_format = piece_data.get("format", "ogg")
    try:
        duration_seconds = get_audio_duration(audio_content, format=audio_format)
        print(f"  Duration: {int(duration_seconds)}s ({int(duration_seconds // 60)}:{int(duration_seconds % 60):02d})")
    except Exception as e:
        print(f"  ERROR reading audio duration: {e}")
        # Use provided duration as fallback
        duration_seconds = piece_data.get("duration_seconds", 180)

    # Upload to MinIO
    try:
        print(f"  Uploading to MinIO ({piece_data['s3_key']})...")
        storage = get_minio_storage()
        await storage.ensure_bucket_exists()

        content_type = "audio/ogg" if audio_format == "ogg" else "audio/mpeg"
        result = await storage.upload_bytes(
            audio_content,
            piece_data["s3_key"],
            content_type=content_type
        )
        print(f"  Uploaded {result['size_bytes']} bytes")
    except Exception as e:
        print(f"  ERROR uploading to MinIO: {e}")
        return False

    # Create database record
    try:
        async with async_session() as session:
            music_piece = MusicPiece(
                title=piece_data["title"],
                composer=piece_data["composer"],
                description=piece_data.get("description", ""),
                s3_key=piece_data["s3_key"],
                duration_seconds=duration_seconds,
                file_size_bytes=result["size_bytes"],
                day_of_year_start=piece_data.get("day_of_year_start", 1),
                day_of_year_end=piece_data.get("day_of_year_end", 366),
                is_active=True,
            )
            session.add(music_piece)
            await session.commit()
            print(f"  Created database record (ID: {music_piece.id})")
    except Exception as e:
        print(f"  ERROR creating database record: {e}")
        return False

    return True


async def main():
    """Main function to add new music pieces."""
    print("=" * 70)
    print("Morning Drive - Add New Classical Music Pieces")
    print("=" * 70)

    # Initialize database
    print("\n[1/4] Initializing database...")
    await init_db()
    print("  Database initialized.")

    # Check existing pieces
    print("\n[2/4] Checking existing pieces...")
    existing = await get_existing_pieces()
    print(f"  Found {len(existing)} existing pieces:")
    for p in existing:
        print(f"    - {p['title']} by {p['composer']}")

    # Define new pieces to add (10 pieces with variety)
    # All recordings are from Wikimedia Commons - public domain
    NEW_PIECES = [
        # === INSTRUMENTAL - ORCHESTRAL ===
        {
            "title": "Serenade for Strings Op. 22 - Larghetto",
            "composer": "Antonin Dvorak",
            "description": "This Larghetto movement from Dvorak's Serenade for Strings showcases the composer's gift for creating warm, singing melodies. Written in 1875, the piece reflects Dvorak's deep love for Czech folk music while maintaining the elegance of the Classical serenade tradition.",
            "audio_url": "https://upload.wikimedia.org/wikipedia/commons/a/a3/Dvorak_-_Serenade_for_Strings_Op._22_-_Larghetto.ogg",
            "s3_key": "music/dvorak/serenade_strings_larghetto.ogg",
            "format": "ogg",
            "day_of_year_start": 1,
            "day_of_year_end": 366,
        },
        {
            "title": "Passacaglia on a Theme by Handel",
            "composer": "Johan Halvorsen",
            "description": "Norwegian composer Halvorsen created this virtuosic duet for violin and viola (or cello) in 1894, based on the final movement of Handel's Harpsichord Suite No. 7. It has become a beloved showpiece that bridges the Baroque and Romantic eras.",
            "audio_url": "https://upload.wikimedia.org/wikipedia/commons/d/dc/Johan_Halvorsen_-_Passacaglia_on_a_theme_by_Handel.ogg",
            "s3_key": "music/halvorsen/passacaglia_handel.ogg",
            "format": "ogg",
            "day_of_year_start": 1,
            "day_of_year_end": 366,
        },
        # === INSTRUMENTAL - PIANO ===
        {
            "title": "Intermezzo Op. 117 No. 1",
            "composer": "Johannes Brahms",
            "description": "Brahms composed this gentle intermezzo in 1892 near the end of his life. He described it as a lullaby to his sorrows, quoting a Scottish ballad. The piece is considered one of his most intimate and tender piano works.",
            "audio_url": "https://upload.wikimedia.org/wikipedia/commons/8/8d/Brahms_-_Intermezzo%2C_Op._117%2C_No._1.ogg",
            "s3_key": "music/brahms/intermezzo_op117_no1.ogg",
            "format": "ogg",
            "day_of_year_start": 1,
            "day_of_year_end": 366,
        },
        {
            "title": "Rhapsody Op. 119 No. 4",
            "composer": "Johannes Brahms",
            "description": "The final work in Brahms's last set of piano pieces (Op. 119), this rhapsody is passionate and dramatic. Written in 1893, it represents Brahms at his most powerful while still maintaining the intimacy characteristic of his late piano works.",
            "audio_url": "https://upload.wikimedia.org/wikipedia/commons/7/72/Brahms_opus119_rhapsodie.ogg",
            "s3_key": "music/brahms/rhapsody_op119_no4.ogg",
            "format": "ogg",
            "day_of_year_start": 1,
            "day_of_year_end": 366,
        },
        {
            "title": "Etincelles (Sparks) Op. 36 No. 6",
            "composer": "Moritz Moszkowski",
            "description": "This sparkling piano etude lives up to its name with brilliant, shimmering passages. Moszkowski was one of the most celebrated pianist-composers of the late 19th century, and this piece showcases his gift for creating virtuosic yet accessible music.",
            "audio_url": "https://upload.wikimedia.org/wikipedia/commons/1/13/Moszkowski_Etincelles_No6.ogg",
            "s3_key": "music/moszkowski/etincelles.ogg",
            "format": "ogg",
            "day_of_year_start": 1,
            "day_of_year_end": 366,
        },
        # === INSTRUMENTAL - GUITAR ===
        {
            "title": "Recuerdos de la Alhambra",
            "composer": "Francisco Tarrega",
            "description": "This tremolo masterpiece evokes the fountains and architecture of the Alhambra palace in Granada. Composed around 1896, it has become one of the most beloved pieces in the classical guitar repertoire, requiring exceptional control of the tremolo technique.",
            "audio_url": "https://upload.wikimedia.org/wikipedia/commons/a/a3/Recuerdos_de_la_Alhambra.ogg",
            "s3_key": "music/tarrega/recuerdos_alhambra.ogg",
            "format": "ogg",
            "day_of_year_start": 1,
            "day_of_year_end": 366,
        },
        # === VOCAL - ART SONGS ===
        {
            "title": "An die Musik (To Music)",
            "composer": "Franz Schubert",
            "description": "This beloved song from 1817 is Schubert's heartfelt tribute to music itself. With text by his friend Franz von Schober, it expresses gratitude to music for providing solace and joy in difficult times - a sentiment that resonates with listeners to this day.",
            "audio_url": "https://upload.wikimedia.org/wikipedia/commons/c/c2/An_die_Musik_%28Schubert_D.547%29.ogg",
            "s3_key": "music/schubert/an_die_musik.ogg",
            "format": "ogg",
            "day_of_year_start": 1,
            "day_of_year_end": 366,
        },
        {
            "title": "Wiegenlied (Lullaby)",
            "composer": "Johannes Brahms",
            "description": "Perhaps the most famous lullaby ever written, Brahms composed this in 1868 for the newborn son of a friend. This historic 1915 recording by legendary contralto Ernestine Schumann-Heink captures the tender, rocking quality that has made this piece a timeless classic.",
            "audio_url": "https://upload.wikimedia.org/wikipedia/commons/8/87/Brahms_-_Schumann-Heink_-_Wiegenlied_%28Berceuse%29_%281915%29.ogg",
            "s3_key": "music/brahms/wiegenlied_schumann_heink.ogg",
            "format": "ogg",
            "day_of_year_start": 1,
            "day_of_year_end": 366,
        },
        {
            "title": "Der Musensohn (The Son of the Muses)",
            "composer": "Franz Schubert",
            "description": "This joyful song from 1822 sets Goethe's poem about a wandering minstrel who brings music wherever he goes. Its infectious energy and dancing rhythm make it one of Schubert's most exuberant songs.",
            "audio_url": "https://upload.wikimedia.org/wikipedia/commons/1/11/Der_Musensohn.ogg",
            "s3_key": "music/schubert/der_musensohn.ogg",
            "format": "ogg",
            "day_of_year_start": 1,
            "day_of_year_end": 366,
        },
        # === CHORAL ===
        {
            "title": "In stiller Nacht (Wondrous Cool)",
            "composer": "Johannes Brahms",
            "description": "This exquisite a cappella choral piece from Brahms's German Folk Songs collection features rich harmonies and a deeply contemplative mood. The text, from an old German folk song, speaks of love and longing under the quiet night sky.",
            "audio_url": "https://upload.wikimedia.org/wikipedia/commons/f/f3/Brahms_Wondrous_cool_Sung_by_the_dwsChorale.ogg",
            "s3_key": "music/brahms/in_stiller_nacht.ogg",
            "format": "ogg",
            "day_of_year_start": 1,
            "day_of_year_end": 366,
        },
    ]

    # Add new pieces
    print(f"\n[3/4] Adding {len(NEW_PIECES)} new pieces...")
    added_count = 0
    failed_pieces = []

    for piece in NEW_PIECES:
        success = await add_music_piece(piece)
        if success:
            added_count += 1
        else:
            failed_pieces.append(piece["title"])

    # Summary
    print("\n" + "=" * 70)
    print("[4/4] Summary")
    print("=" * 70)
    print(f"  Added: {added_count} pieces")
    print(f"  Failed/Skipped: {len(failed_pieces)} pieces")

    if failed_pieces:
        print("\n  Failed pieces:")
        for title in failed_pieces:
            print(f"    - {title}")

    # Final count
    async with async_session() as session:
        result = await session.execute(select(MusicPiece).where(MusicPiece.is_active == True))
        pieces = result.scalars().all()
        print(f"\n  Total active music pieces in database: {len(pieces)}")
        for p in pieces:
            duration_str = f"{int(p.duration_seconds // 60)}:{int(p.duration_seconds % 60):02d}"
            print(f"    - {p.title} by {p.composer} ({duration_str})")

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
