"""Blob storage: Cloudflare R2 (S3-compatible) in prod, local disk in dev."""

import asyncio
from pathlib import Path

import boto3

from app.config import get_settings


class Storage:
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def presigned_url(self, key: str, expires_s: int = 900) -> str | None: ...


class S3Storage(Storage):
    def __init__(self) -> None:
        s = get_settings()
        self._bucket = s.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            aws_access_key_id=s.s3_access_key_id,
            aws_secret_access_key=s.s3_secret_access_key,
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket, Key=key, Body=data, ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        resp = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
        return await asyncio.to_thread(resp["Body"].read)

    async def presigned_url(self, key: str, expires_s: int = 900) -> str | None:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_s,
        )


class LocalStorage(Storage):
    def __init__(self) -> None:
        self._root = Path(get_settings().local_blob_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self._root / key).resolve()
        if not p.is_relative_to(self._root.resolve()):
            raise ValueError(f"Invalid blob key: {key}")
        return p

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(p.write_bytes, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def presigned_url(self, key: str, expires_s: int = 900) -> str | None:
        return None  # dev mode: clients download via the API instead


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = S3Storage() if get_settings().s3_endpoint_url else LocalStorage()
    return _storage
