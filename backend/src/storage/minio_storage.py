"""MinIO storage service for music files."""

import asyncio
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional

from minio import Minio
from minio.error import S3Error

from src.config import get_settings


class MinioStorage:
    """Service for interacting with MinIO storage."""

    def __init__(self):
        settings = get_settings()
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.bucket = settings.minio_bucket

    async def ensure_bucket_exists(self) -> None:
        """Create the bucket if it doesn't exist."""
        def _ensure():
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                print(f"Created MinIO bucket: {self.bucket}")
            else:
                print(f"MinIO bucket exists: {self.bucket}")

        await asyncio.to_thread(_ensure)

    async def upload_file(
        self,
        file_path: Path,
        s3_key: str,
        content_type: str = "audio/mpeg",
    ) -> dict:
        """Upload a file to MinIO.

        Args:
            file_path: Local path to the file
            s3_key: Key (path) in the bucket
            content_type: MIME type of the file

        Returns:
            Dict with file info including size
        """
        def _upload():
            with open(file_path, "rb") as f:
                data = f.read()
                size = len(data)

            self.client.put_object(
                self.bucket,
                s3_key,
                BytesIO(data),
                length=size,
                content_type=content_type,
            )
            return {"s3_key": s3_key, "size_bytes": size}

        return await asyncio.to_thread(_upload)

    async def upload_bytes(
        self,
        data: bytes,
        s3_key: str,
        content_type: str = "audio/mpeg",
    ) -> dict:
        """Upload bytes directly to MinIO.

        Args:
            data: File content as bytes
            s3_key: Key (path) in the bucket
            content_type: MIME type of the file

        Returns:
            Dict with file info including size
        """
        def _upload():
            size = len(data)
            self.client.put_object(
                self.bucket,
                s3_key,
                BytesIO(data),
                length=size,
                content_type=content_type,
            )
            return {"s3_key": s3_key, "size_bytes": size}

        return await asyncio.to_thread(_upload)

    async def download_to_file(self, s3_key: str, dest_path: Path) -> Path:
        """Download a file from MinIO to local path.

        Args:
            s3_key: Key (path) in the bucket
            dest_path: Local destination path

        Returns:
            Path to downloaded file
        """
        def _download():
            self.client.fget_object(self.bucket, s3_key, str(dest_path))
            return dest_path

        return await asyncio.to_thread(_download)

    async def get_file_bytes(self, s3_key: str) -> bytes:
        """Get file content as bytes.

        Args:
            s3_key: Key (path) in the bucket

        Returns:
            File content as bytes
        """
        def _get():
            response = self.client.get_object(self.bucket, s3_key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await asyncio.to_thread(_get)

    async def file_exists(self, s3_key: str) -> bool:
        """Check if a file exists in the bucket.

        Args:
            s3_key: Key (path) in the bucket

        Returns:
            True if file exists
        """
        def _exists():
            try:
                self.client.stat_object(self.bucket, s3_key)
                return True
            except S3Error:
                return False

        return await asyncio.to_thread(_exists)

    async def delete_file(self, s3_key: str) -> bool:
        """Delete a file from MinIO.

        Args:
            s3_key: Key (path) in the bucket

        Returns:
            True if deleted successfully
        """
        def _delete():
            try:
                self.client.remove_object(self.bucket, s3_key)
                return True
            except S3Error:
                return False

        return await asyncio.to_thread(_delete)

    async def list_files(self, prefix: str = "") -> list[dict]:
        """List files in the bucket.

        Args:
            prefix: Optional prefix to filter files

        Returns:
            List of file info dicts
        """
        def _list():
            objects = self.client.list_objects(self.bucket, prefix=prefix)
            return [
                {
                    "key": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                }
                for obj in objects
            ]

        return await asyncio.to_thread(_list)

    def get_presigned_url(self, s3_key: str, expires_hours: int = 1) -> str:
        """Get a presigned URL for direct access to a file.

        Args:
            s3_key: Key (path) in the bucket
            expires_hours: Hours until URL expires

        Returns:
            Presigned URL string
        """
        return self.client.presigned_get_object(
            self.bucket,
            s3_key,
            expires=timedelta(hours=expires_hours),
        )

    def get_file_stream(self, s3_key: str):
        """Get a streaming response for a file.

        Args:
            s3_key: Key (path) in the bucket

        Returns:
            MinIO response object (use as iterator, must close after use)
        """
        return self.client.get_object(self.bucket, s3_key)

    def get_file_stat(self, s3_key: str):
        """Get file metadata/stats.

        Args:
            s3_key: Key (path) in the bucket

        Returns:
            Object stat info
        """
        return self.client.stat_object(self.bucket, s3_key)


# Singleton instance
_storage: Optional[MinioStorage] = None


def get_minio_storage() -> MinioStorage:
    """Get the MinIO storage singleton."""
    global _storage
    if _storage is None:
        _storage = MinioStorage()
    return _storage
