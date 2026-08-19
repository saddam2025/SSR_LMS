"""Private asset storage backed by a Railway persistent volume.

R2/S3 support has been removed. All protected assets (PDFs, protected docs, etc.)
live on local disk under LOCAL_MEDIA_ROOT, which should be mounted to a Railway
volume in production so it survives redeploys.

Note: Cloudflare Stream (video) is a separate system — see cloudflare_stream.py /
cloudflare_upload.py — and is unaffected by this module.
"""
import os, uuid, shutil
from pathlib import Path

ROOT = Path(os.getenv("LOCAL_MEDIA_ROOT", "media/uploads")).resolve()


def _key_for(original_name: str, prefix: str = "protected") -> str:
    safe_ext = Path(original_name).suffix.lower()[:10]
    clean_prefix = (prefix or "protected").strip("/") or "protected"
    return f"{clean_prefix}/{uuid.uuid4().hex}{safe_ext}"


def new_storage_key(original_name: str, prefix: str = "protected") -> str:
    return _key_for(original_name, prefix)


def _resolve_path(key: str) -> Path:
    path = (ROOT / key).resolve()
    if ROOT not in path.parents:
        raise RuntimeError("Invalid storage path")
    return path


def save_upload_file(fileobj, original_name: str):
    """Stream a spooled upload to the local volume without loading it fully into RAM."""
    key = _key_for(original_name)
    fileobj.seek(0)
    path = _resolve_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as out:
        shutil.copyfileobj(fileobj, out, length=1024 * 1024)
    return key, "local"


def save_upload(data: bytes, original_name: str):
    from io import BytesIO
    return save_upload_file(BytesIO(data), original_name)


def head_private(key: str) -> dict:
    path = _resolve_path(key)
    if not path.exists():
        raise FileNotFoundError(key)
    return {"ContentLength": path.stat().st_size, "ContentType": "application/octet-stream"}


def read_private_range(key: str, start: int = 0, end: int = 63) -> bytes:
    path = _resolve_path(key)
    if not path.exists():
        raise FileNotFoundError(key)
    with path.open("rb") as fh:
        fh.seek(max(0, start))
        return fh.read(max(0, end - start + 1))


def download_private_to_file(key: str, fileobj) -> None:
    fileobj.seek(0)
    fileobj.truncate(0)
    path = _resolve_path(key)
    if not path.exists():
        raise FileNotFoundError(key)
    with path.open("rb") as src:
        shutil.copyfileobj(src, fileobj, length=1024 * 1024)
    fileobj.seek(0)


def read_private_bytes(key: str, max_bytes: int = 60 * 1024 * 1024) -> bytes:
    path = _resolve_path(key)
    if not path.exists():
        raise FileNotFoundError(key)
    if path.stat().st_size > max_bytes:
        raise ValueError("asset_too_large_for_dynamic_watermark")
    return path.read_bytes()


def delete_private(key: str, provider: str | None = None) -> None:
    path = _resolve_path(key)
    if path.exists():
        path.unlink()


def verify_storage_roundtrip() -> None:
    """Verify the Railway volume is writable before receiving students.

    A production deploy should fail fast if LOCAL_MEDIA_ROOT isn't a writable,
    persistent mount. The probe file is tiny and always removed in a finally block.
    """
    key = f"healthchecks/{uuid.uuid4().hex}.txt"
    payload = b"mostashar-storage-ok"
    path = _resolve_path(key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        if path.read_bytes() != payload:
            raise RuntimeError("Storage roundtrip returned unexpected content")
    finally:
        try:
            path.unlink()
        except Exception:
            pass