from __future__ import annotations

from io import BytesIO


def stream_state(result: dict) -> tuple[str, float, str, str]:
    status = result.get("status") or {}
    state = str(status.get("state") or "processing").lower()
    try:
        percent = max(0.0, min(100.0, float(status.get("pctComplete") or 0)))
    except (TypeError, ValueError):
        percent = 0.0
    error_code = str(status.get("errorReasonCode") or status.get("errReasonCode") or "")[:120]
    error_text = str(status.get("errorReasonText") or status.get("errReasonText") or "")[:300]
    return state, percent, error_code, error_text


def valid_upload_signature(data: bytes, mime: str) -> bool:
    if mime == "application/pdf":
        return data.startswith(b"%PDF-")
    if mime == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if mime == "video/mp4":
        return len(data) >= 12 and data[4:8] == b"ftyp"
    if mime == "video/webm":
        return data.startswith(b"\x1aE\xdf\xa3")
    return False


def validate_upload_structure(file_obj, mime: str) -> None:
    pos = file_obj.tell()
    try:
        file_obj.seek(0)
        if mime in {"image/png", "image/jpeg"}:
            from PIL import Image
            try:
                with Image.open(file_obj) as img:
                    if img.width * img.height > 40_000_000:
                        raise ValueError("image_too_large")
                    img.verify()
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError("invalid_image") from exc
        elif mime == "application/pdf":
            from pypdf import PdfReader
            try:
                reader = PdfReader(file_obj, strict=False)
                if reader.is_encrypted:
                    raise ValueError("encrypted_pdf")
                pages = len(reader.pages)
                if pages <= 0:
                    raise ValueError("empty_pdf")
                if pages > 500:
                    raise ValueError("too_many_pages")
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError("invalid_pdf") from exc
    finally:
        file_obj.seek(pos)


def media_return_path(course_id: int, lesson_id: int, requested: str) -> str:
    allowed = {
        f"/admin/course/{course_id}#media-library",
        f"/admin/lesson/{lesson_id}/edit#lesson-media",
    }
    return requested if requested in allowed else f"/admin/course/{course_id}#media-library"


def normalize_media_type(filename: str, declared_mime: str) -> tuple[str, str]:
    import os
    original_ext = os.path.splitext(filename)[1].lower()
    mime_aliases = {"image/jpg": "image/jpeg", "application/x-pdf": "application/pdf"}
    normalized = mime_aliases.get((declared_mime or "").lower().strip(), (declared_mime or "").lower().strip())
    extension_mimes = {
        ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".mp4": "video/mp4", ".webm": "video/webm",
    }
    if normalized in {"", "application/octet-stream"}:
        normalized = extension_mimes.get(original_ext, "")
    return normalized, extension_mimes.get(original_ext, "")
