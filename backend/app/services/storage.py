from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import boto3
from botocore.client import BaseClient
from fastapi import UploadFile

from app.core.config import settings

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _local_storage_root() -> Path:
    root = Path(settings.local_storage_dir)
    return root if root.is_absolute() else (_BACKEND_DIR / root).resolve()


def _build_s3_client() -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def upload_to_s3(upload: UploadFile) -> tuple[str, str, str]:
    suffix = Path(upload.filename or "audio.bin").suffix
    key = f"recordings/{uuid4()}{suffix}"
    mime = upload.content_type or "application/octet-stream"
    payload = upload.file.read()

    if settings.s3_enabled:
        client = _build_s3_client()
        client.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=payload,
            ContentType=mime,
        )
        return settings.s3_bucket, key, mime

    # Local fallback for fast local dev/smoke test.
    target = _local_storage_root() / settings.s3_bucket / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return settings.s3_bucket, key, mime


def read_object_bytes(bucket: str, key: str) -> bytes:
    if settings.s3_enabled:
        client = _build_s3_client()
        data = client.get_object(Bucket=bucket, Key=key)
        body = data.get("Body")
        if not body:
            raise ValueError("Missing S3 object body")
        return body.read()

    source = _local_storage_root() / bucket / key
    if not source.exists():
        raise FileNotFoundError(f"Object not found: {bucket}/{key}")
    return source.read_bytes()


def delete_object(bucket: str, key: str) -> None:
    if settings.s3_enabled:
        client = _build_s3_client()
        client.delete_object(Bucket=bucket, Key=key)
        return

    source = _local_storage_root() / bucket / key
    if source.exists():
        source.unlink()
