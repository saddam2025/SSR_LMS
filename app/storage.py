import os, uuid, shutil
from pathlib import Path

ROOT = Path(os.getenv("LOCAL_MEDIA_ROOT", "media/uploads")).resolve()


def mode():
    # Kept as a function (not a constant) so existing callers/imports don't break.
    # R2/S3 support has been removed from this build — local disk (a Railway
    # Volume in production) is the only supported backend.
    return "local"


def _key_for(original_name: str) -> str:
    safe_ext = Path(original_name).suffix.lower()[:10]
    return f"protected/{uuid.uuid4().hex}{safe_ext}"


def save_upload_file(fileobj, original_name: str):
    """Stream a spooled upload to private local storage without loading the whole file into RAM."""
    key = _key_for(original_name)
    fileobj.seek(0)
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


def read_private_bytes(key: str, max_bytes: int = 60 * 1024 * 1024) -> bytes:
    path = (ROOT / key).resolve()
    if ROOT not in path.parents or not path.exists():
        raise FileNotFoundError(key)
    if path.stat().st_size > max_bytes:
        raise ValueError("asset_too_large_for_dynamic_watermark")
    return path.read_bytes()


def delete_private(key: str, provider: str | None = None) -> None:
    path = (ROOT / key).resolve()
    if ROOT not in path.parents:
        raise RuntimeError("Invalid storage path")
    if path.exists():
        path.unlink()