"""Music API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import MusicPieceListResponse, MusicPieceResponse, MusicPieceUpdate
from src.storage.database import MusicPiece, get_session
from src.storage.minio_storage import get_minio_storage


router = APIRouter()


@router.get("/music", response_model=MusicPieceListResponse)
async def list_music_pieces(
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
):
    """List all available music pieces."""
    query = select(MusicPiece)
    if active_only:
        query = query.where(MusicPiece.is_active == True)
    query = query.order_by(MusicPiece.composer, MusicPiece.title)

    result = await session.execute(query)
    pieces = result.scalars().all()

    return MusicPieceListResponse(
        pieces=[
            MusicPieceResponse(
                id=p.id,
                created_at=p.created_at,
                title=p.title,
                composer=p.composer,
                description=p.description,
                s3_key=p.s3_key,
                duration_seconds=p.duration_seconds,
                file_size_bytes=p.file_size_bytes,
                day_of_year_start=p.day_of_year_start,
                day_of_year_end=p.day_of_year_end,
                is_active=p.is_active,
            )
            for p in pieces
        ],
        total=len(pieces),
    )


@router.get("/music/{piece_id}", response_model=MusicPieceResponse)
async def get_music_piece(
    piece_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get a specific music piece by ID."""
    result = await session.execute(select(MusicPiece).where(MusicPiece.id == piece_id))
    piece = result.scalar_one_or_none()

    if not piece:
        raise HTTPException(status_code=404, detail="Music piece not found")

    return MusicPieceResponse(
        id=piece.id,
        created_at=piece.created_at,
        title=piece.title,
        composer=piece.composer,
        description=piece.description,
        s3_key=piece.s3_key,
        duration_seconds=piece.duration_seconds,
        file_size_bytes=piece.file_size_bytes,
        day_of_year_start=piece.day_of_year_start,
        day_of_year_end=piece.day_of_year_end,
        is_active=piece.is_active,
    )


@router.post("/music", response_model=MusicPieceResponse)
async def upload_music_piece(
    title: str,
    composer: str,
    duration_seconds: float,
    file: UploadFile,
    description: Optional[str] = None,
    day_of_year_start: int = 1,
    day_of_year_end: int = 366,
    session: AsyncSession = Depends(get_session),
):
    """Upload a new music piece with audio file to MinIO."""
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title).strip()
    safe_composer = "".join(c if c.isalnum() or c in " -_" else "" for c in composer).strip()
    s3_key = f"music/{safe_composer}/{safe_title}.mp3".replace(" ", "_").lower()

    content = await file.read()
    if len(content) < 10000:
        raise HTTPException(status_code=400, detail="File too small to be valid audio")

    storage = get_minio_storage()
    await storage.ensure_bucket_exists()
    result = await storage.upload_bytes(content, s3_key, content_type=file.content_type or "audio/mpeg")

    piece = MusicPiece(
        title=title,
        composer=composer,
        description=description,
        s3_key=s3_key,
        duration_seconds=duration_seconds,
        file_size_bytes=result["size_bytes"],
        day_of_year_start=day_of_year_start,
        day_of_year_end=day_of_year_end,
        is_active=True,
    )
    session.add(piece)
    await session.commit()
    await session.refresh(piece)

    return MusicPieceResponse(
        id=piece.id,
        created_at=piece.created_at,
        title=piece.title,
        composer=piece.composer,
        description=piece.description,
        s3_key=piece.s3_key,
        duration_seconds=piece.duration_seconds,
        file_size_bytes=piece.file_size_bytes,
        day_of_year_start=piece.day_of_year_start,
        day_of_year_end=piece.day_of_year_end,
        is_active=piece.is_active,
    )


@router.put("/music/{piece_id}", response_model=MusicPieceResponse)
async def update_music_piece(
    piece_id: int,
    update: MusicPieceUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update music piece metadata."""
    result = await session.execute(select(MusicPiece).where(MusicPiece.id == piece_id))
    piece = result.scalar_one_or_none()

    if not piece:
        raise HTTPException(status_code=404, detail="Music piece not found")

    update_data = update.model_dump(exclude_unset=True)
    if "title" in update_data:
        piece.title = update_data["title"]
    if "composer" in update_data:
        piece.composer = update_data["composer"]
    if "description" in update_data:
        piece.description = update_data["description"]
    if "day_of_year_start" in update_data:
        piece.day_of_year_start = update_data["day_of_year_start"]
    if "day_of_year_end" in update_data:
        piece.day_of_year_end = update_data["day_of_year_end"]
    if "is_active" in update_data:
        piece.is_active = update_data["is_active"]

    await session.commit()
    await session.refresh(piece)

    return MusicPieceResponse(
        id=piece.id,
        created_at=piece.created_at,
        title=piece.title,
        composer=piece.composer,
        description=piece.description,
        s3_key=piece.s3_key,
        duration_seconds=piece.duration_seconds,
        file_size_bytes=piece.file_size_bytes,
        day_of_year_start=piece.day_of_year_start,
        day_of_year_end=piece.day_of_year_end,
        is_active=piece.is_active,
    )


@router.delete("/music/{piece_id}")
async def delete_music_piece(
    piece_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a music piece (from both database and MinIO)."""
    result = await session.execute(select(MusicPiece).where(MusicPiece.id == piece_id))
    piece = result.scalar_one_or_none()

    if not piece:
        raise HTTPException(status_code=404, detail="Music piece not found")

    storage = get_minio_storage()
    await storage.delete_file(piece.s3_key)

    await session.delete(piece)
    await session.commit()

    return {"status": "deleted", "id": piece_id}


@router.get("/music/{piece_id}/stream")
async def stream_music_piece(
    piece_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Stream a music piece audio file."""
    result = await session.execute(select(MusicPiece).where(MusicPiece.id == piece_id))
    piece = result.scalar_one_or_none()

    if not piece:
        raise HTTPException(status_code=404, detail="Music piece not found")

    storage = get_minio_storage()

    if not await storage.file_exists(piece.s3_key):
        raise HTTPException(status_code=404, detail="Audio file not found in storage")

    def iter_file():
        response = storage.get_file_stream(piece.s3_key)
        try:
            for chunk in response.stream(32 * 1024):
                yield chunk
        finally:
            response.close()
            response.release_conn()

    return StreamingResponse(
        iter_file(),
        media_type="audio/mpeg",
        headers={
            "Content-Length": str(piece.file_size_bytes),
            "Accept-Ranges": "bytes",
        }
    )

