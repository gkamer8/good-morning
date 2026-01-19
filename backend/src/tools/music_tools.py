"""Tools for fetching music from the database and MinIO storage."""

import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select, and_

from src.config import get_settings
from src.storage.database import MusicPiece, async_session
from src.storage.minio_storage import get_minio_storage


@dataclass
class MusicPieceInfo:
    """Information about a music piece for use in briefings."""

    id: int
    composer: str
    title: str
    description: Optional[str]
    duration_seconds: float
    s3_key: str


async def get_available_music_pieces(day_of_year: Optional[int] = None) -> list[MusicPieceInfo]:
    """Get all available music pieces, optionally filtered by day of year.

    Args:
        day_of_year: Day of year (1-366) to filter pieces by their seasonal range.
                     If None, returns all active pieces.

    Returns:
        List of MusicPieceInfo objects for available pieces.
    """
    async with async_session() as session:
        query = select(MusicPiece).where(MusicPiece.is_active == True)

        if day_of_year is not None:
            # Filter by day of year range
            # Handle wrap-around (e.g., winter pieces that span Dec-Jan)
            query = query.where(
                and_(
                    MusicPiece.day_of_year_start <= day_of_year,
                    MusicPiece.day_of_year_end >= day_of_year,
                )
            )

        result = await session.execute(query)
        pieces = result.scalars().all()

        return [
            MusicPieceInfo(
                id=p.id,
                composer=p.composer,
                title=p.title,
                description=p.description,
                duration_seconds=p.duration_seconds,
                s3_key=p.s3_key,
            )
            for p in pieces
        ]


async def get_music_piece_for_date(date_str: str) -> Optional[MusicPieceInfo]:
    """Get a deterministic music piece based on the date.

    This ensures the same piece is returned for the same date,
    providing variety across days while being reproducible.

    Args:
        date_str: Date string in YYYY-MM-DD format.

    Returns:
        MusicPieceInfo if pieces are available, None otherwise.
    """
    # Parse date to get day of year
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        day_of_year = date.timetuple().tm_yday
    except ValueError:
        day_of_year = None

    # Get pieces available for this day
    pieces = await get_available_music_pieces(day_of_year)

    if not pieces:
        # Fall back to all pieces if none match the day filter
        pieces = await get_available_music_pieces(None)

    if not pieces:
        return None

    # Use date hash for deterministic selection
    date_hash = hash(date_str) % len(pieces)
    return pieces[date_hash]


async def get_random_music_piece() -> Optional[MusicPieceInfo]:
    """Get a random music piece from the available pieces.

    Returns:
        MusicPieceInfo if pieces are available, None otherwise.
    """
    pieces = await get_available_music_pieces(None)

    if not pieces:
        return None

    return random.choice(pieces)


async def download_music_audio(
    piece: MusicPieceInfo,
    output_dir: Path,
) -> Optional[Path]:
    """Download music audio from MinIO to the specified directory.

    Args:
        piece: The music piece to download.
        output_dir: Directory to save the file to (managed by caller for cleanup).

    Returns:
        Path to the audio file, or None if download fails.
    """
    # Determine file extension from s3_key
    ext = Path(piece.s3_key).suffix or ".mp3"

    # Download from MinIO to output directory
    print(f"Downloading music: {piece.title} from MinIO ({piece.s3_key})")
    try:
        storage = get_minio_storage()

        # Check if file exists in MinIO
        if not await storage.file_exists(piece.s3_key):
            print(f"Music file not found in MinIO: {piece.s3_key}")
            return None

        # Create file in output directory (managed by orchestrator)
        output_path = output_dir / f"music_{piece.id}{ext}"

        # Download to output path
        await storage.download_to_file(piece.s3_key, output_path)

        # Verify download
        if not output_path.exists() or output_path.stat().st_size < 10000:
            print(f"Downloaded file invalid: {output_path}")
            return None

        print(f"Downloaded music to: {output_path} ({output_path.stat().st_size} bytes)")
        return output_path

    except Exception as e:
        print(f"Error downloading music: {e}")
        return None


def format_music_for_agent(piece: MusicPieceInfo) -> str:
    """Format music info for the script writer agent.

    Args:
        piece: The music piece to format.

    Returns:
        Formatted string for Claude to use when writing the script.
    """
    description_text = ""
    if piece.description:
        description_text = f"\nDescription/Facts:\n{piece.description}"

    duration_minutes = int(piece.duration_seconds // 60)
    duration_str = f"about {duration_minutes} minutes" if duration_minutes > 0 else "less than a minute"

    return f"""=== MUSIC SEGMENT ===
Composer: {piece.composer}
Piece: {piece.title}
Duration: {duration_str}{description_text}

Instructions: Create a brief, engaging introduction to this piece that helps the listener appreciate the music they're about to hear.
{f'Use the description/facts above to make the introduction interesting and educational.' if piece.description else 'Keep the introduction warm and welcoming.'}
The actual music WILL play after your introduction, so end with a smooth transition like:
"And now, here is {piece.title} by {piece.composer}..." or "Let's listen to {piece.title}..."
Keep the introduction under 30 seconds so listeners can enjoy the music.
"""
