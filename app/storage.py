import os, uuid, shutil
from functools import lru_cache
from pathlib import Path

ROOT = Path(os.getenv("LOCAL_MEDIA_ROOT", "media/uploads")).resolve()


def mode():
    return os.getenv("STORAGE_BACKEND", "local").lower()


def _key_for(original_name: str, prefix: str = "protected") -> str:
    safe_ext = Path(original_name).suffix.lower()[:10]
    clean_prefix = (prefix or "protected").strip("/") or "protected"
    return f"{clean_prefix}/{uuid.uuid4().hex}{safe_ext}"


def new_storage_key(original_name: str, prefix: str = "protected") -> str:
    return _key_for(original_name, prefix)


def _s3_region() -> str | None:
    configured = os.getenv("S3_REGION", "").strip()
    if configured:
        return configured
    endpoint = os.getenv("S3_ENDPOINT_URL", "").lower()
    return "auto" if ".r2.cloudflarestorage.com" in endpoint else None


@lru_cache(maxsize=1)
def s3_client():
    """Create one tuned S3-compatible client per worker.

    Reusing the client keeps HTTP connections pooled instead of opening a new TLS
    connection for every upload/download. This matters once many students are
    requesting protected assets concurrently.
    """
    import boto3
    from botocore.config import Config

    max_connections = max(4, min(int(os.getenv("S3_MAX_POOL_CONNECTIONS", "32")), 128))
    connect_timeout = max(2, min(int(os.getenv("S3_CONNECT_TIMEOUT_SECONDS", "5")), 30))
    read_timeout = max(10, min(int(os.getenv("S3_READ_TIMEOUT_SECONDS", "90")), 300))
    config = Config(
        signature_version="s3v4",
        max_pool_connections=max_connections,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        retries={"max_attempts": 5, "mode": "adaptive"},
        tcp_keepalive=True,
    )
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL") or None,
        region_name=_s3_region(),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
        config=config,
    )


def s3_ready() -> bool:
    return mode() == "s3" and all(
        os.getenv(name, "").strip()
        for name in ("S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
    )


def save_upload_file(fileobj, original_name: str):
    """Stream a spooled upload to private storage without loading the whole file into RAM."""
    key = _key_for(original_name)
    fileobj.seek(0)
    if mode() == "s3":
        from boto3.s3.transfer import TransferConfig

        # Protected documents are capped at 60 MB. Multipart uploads with a small
        # amount of concurrency are substantially more resilient than one giant PUT.
        transfer = TransferConfig(
            multipart_threshold=8 * 1024 * 1024,
            multipart_chunksize=8 * 1024 * 1024,
            max_concurrency=max(1, min(int(os.getenv("S3_UPLOAD_CONCURRENCY", "4")), 8)),
            use_threads=True,
        )
        s3_client().upload_fileobj(
            fileobj,
            os.environ["S3_BUCKET"],
            key,
            ExtraArgs={"ContentType": "application/octet-stream"},
            Config=transfer,
        )
        return key, "s3"
    path = (ROOT / key).resolve()
    if ROOT not in path.parents:
        raise RuntimeError("Invalid storage path")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as out:
        shutil.copyfileobj(fileobj, out, length=1024 * 1024)
    return key, "local"


def save_upload(data: bytes, original_name: str):
    from io import BytesIO
    return save_upload_file(BytesIO(data), original_name)


def presigned_get(key: str, expires=180):
    return s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": os.environ["S3_BUCKET"], "Key": key},
        ExpiresIn=expires,
    )


def presigned_put(key: str, content_type: str, expires: int = 900) -> str:
    """Create a short-lived browser upload URL for R2/S3.

    ContentType is part of the signature, so the browser cannot silently upload a
    different declared type with the same URL.
    """
    return s3_client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": os.environ["S3_BUCKET"],
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=max(60, min(int(expires), 3600)),
        HttpMethod="PUT",
    )


def head_private(key: str) -> dict:
    if mode() != "s3":
        path = (ROOT / key).resolve()
        if ROOT not in path.parents or not path.exists():
            raise FileNotFoundError(key)
        return {"ContentLength": path.stat().st_size, "ContentType": "application/octet-stream"}
    return s3_client().head_object(Bucket=os.environ["S3_BUCKET"], Key=key)


def read_private_range(key: str, start: int = 0, end: int = 63) -> bytes:
    if mode() != "s3":
        path = (ROOT / key).resolve()
        if ROOT not in path.parents or not path.exists():
            raise FileNotFoundError(key)
        with path.open("rb") as fh:
            fh.seek(max(0, start))
            return fh.read(max(0, end - start + 1))
    obj = s3_client().get_object(
        Bucket=os.environ["S3_BUCKET"],
        Key=key,
        Range=f"bytes={max(0, start)}-{max(start, end)}",
    )
    return obj["Body"].read()


def download_private_to_file(key: str, fileobj) -> None:
    fileobj.seek(0)
    fileobj.truncate(0)
    if mode() == "s3":
        s3_client().download_fileobj(os.environ["S3_BUCKET"], key, fileobj)
    else:
        path = (ROOT / key).resolve()
        if ROOT not in path.parents or not path.exists():
            raise FileNotFoundError(key)
        with path.open("rb") as src:
            shutil.copyfileobj(src, fileobj, length=1024 * 1024)
    fileobj.seek(0)


def read_private_bytes(key: str, max_bytes: int = 60 * 1024 * 1024) -> bytes:
    if mode() == "s3":
        obj = s3_client().get_object(Bucket=os.environ["S3_BUCKET"], Key=key)
        size = int(obj.get("ContentLength") or 0)
        if size > max_bytes:
            raise ValueError("asset_too_large_for_dynamic_watermark")
        data = obj["Body"].read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("asset_too_large_for_dynamic_watermark")
        return data
    path = (ROOT / key).resolve()
    if ROOT not in path.parents or not path.exists():
        raise FileNotFoundError(key)
    if path.stat().st_size > max_bytes:
        raise ValueError("asset_too_large_for_dynamic_watermark")
    return path.read_bytes()


def delete_private(key: str, provider: str | None = None) -> None:
    provider = (provider or mode()).lower()
    if provider == "s3":
        s3_client().delete_object(Bucket=os.environ["S3_BUCKET"], Key=key)
        return
    path = (ROOT / key).resolve()
    if ROOT not in path.parents:
        raise RuntimeError("Invalid storage path")
    if path.exists():
        path.unlink()


def verify_storage_roundtrip() -> None:
    """Verify the exact Put/Get/Delete permissions the application needs.

    A production deploy should fail before receiving students if the R2 bucket or
    credentials are wrong. The probe is tiny and always removed in a finally block.
    """
    if mode() != "s3":
        return
    key = f"healthchecks/{uuid.uuid4().hex}.txt"
    payload = b"mostashar-storage-ok"
    c = s3_client()
    try:
        c.put_object(Bucket=os.environ["S3_BUCKET"], Key=key, Body=payload, ContentType="text/plain")
        result = c.get_object(Bucket=os.environ["S3_BUCKET"], Key=key)
        if result["Body"].read(len(payload) + 1) != payload:
            raise RuntimeError("Storage roundtrip returned unexpected content")
    finally:
        try:
            c.delete_object(Bucket=os.environ["S3_BUCKET"], Key=key)
        except Exception:
            pass
