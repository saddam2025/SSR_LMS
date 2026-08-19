from io import BytesIO
from contextlib import contextmanager
import os
import threading
from datetime import datetime, timezone
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color
from PIL import Image, ImageDraw, ImageFont


class WatermarkCapacityExceeded(RuntimeError):
    pass


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(value, high))


_WATERMARK_MAX_CONCURRENT = _bounded_int("WATERMARK_MAX_CONCURRENT", 2, 1, 8)
_WATERMARK_ACQUIRE_TIMEOUT = _bounded_int("WATERMARK_ACQUIRE_TIMEOUT_SECONDS", 5, 1, 30)
_WATERMARK_SLOTS = threading.BoundedSemaphore(_WATERMARK_MAX_CONCURRENT)


@contextmanager
def watermark_capacity():
    """Bound RAM/CPU-heavy dynamic watermark operations per web process.

    Protected documents are intentionally generated per student/session. A burst of
    large PDFs/images can otherwise multiply memory usage and make the whole Railway
    instance unhealthy. Fail fast with a retryable error instead of risking OOM.
    """
    acquired = _WATERMARK_SLOTS.acquire(timeout=_WATERMARK_ACQUIRE_TIMEOUT)
    if not acquired:
        raise WatermarkCapacityExceeded("watermark_capacity_busy")
    try:
        yield
    finally:
        _WATERMARK_SLOTS.release()


def trace_text(user_id: int, email: str, name: str = "") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    who = f"{name[:80]} | " if name else ""
    return f"{who}Authorized Student ID {user_id} | {email[:80]} | {stamp}"


def watermark_pdf(data: bytes, text: str) -> bytes:
    reader = PdfReader(BytesIO(data))
    writer = PdfWriter()
    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        overlay_buf = BytesIO()
        c = canvas.Canvas(overlay_buf, pagesize=(width, height))
        c.setFillColor(Color(0.35, 0.05, 0.12, alpha=0.18))
        c.setFont("Helvetica-Bold", 11)
        c.saveState()
        c.translate(width / 2, height / 2)
        c.rotate(28)
        step_x = max(220, width / 3)
        step_y = 95
        y = -height
        while y < height:
            x = -width
            while x < width:
                c.drawCentredString(x, y, text)
                x += step_x
            y += step_y
        c.restoreState()
        c.save()
        overlay_buf.seek(0)
        overlay = PdfReader(overlay_buf).pages[0]
        page.merge_page(overlay)
        writer.add_page(page)
    out = BytesIO(); writer.write(out)
    return out.getvalue()


import logging

_watermark_logger = logging.getLogger("lms.watermark")

# ImageFont.truetype("DejaVuSans.ttf", size) relies on PIL/fontconfig finding the
# font on the system path, which is not guaranteed inside a minimal container.
# When it's missing, PIL silently falls back to a fixed-size bitmap font that
# IGNORES the `size` argument entirely -- so the size we computed from the
# image's own dimensions (for legibility and crop-resistance) has no effect,
# and every watermark renders at the same tiny size regardless of image
# resolution. Search common locations explicitly instead of trusting the
# implicit lookup, and only fall back to the bitmap font once, loudly.
_FONT_CANDIDATES = (
    "DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "fonts", "DejaVuSans-Bold.ttf"),
)
_font_warned = False


def _font(size: int):
    global _font_warned
    for candidate in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    if not _font_warned:
        _watermark_logger.warning(
            "watermark_font_missing: no TrueType font found in %s; falling back to a fixed-size "
            "bitmap font that ignores the requested size (%d). Install fonts-dejavu-core in the "
            "image or bundle a .ttf under app/static/fonts/ to restore size-scaled watermarks.",
            _FONT_CANDIDATES, size,
        )
        _font_warned = True
    return ImageFont.load_default()


def watermark_image(data: bytes, text: str, output_format: str = "JPEG") -> bytes:
    src = Image.open(BytesIO(data)).convert("RGBA")
    overlay = Image.new("RGBA", src.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(max(14, int(min(src.size) * 0.025)))
    # Repeat at multiple rows so cropping does not trivially remove attribution.
    spacing_y = max(90, int(src.height * 0.14))
    spacing_x = max(260, int(src.width * 0.45))
    for y in range(20, src.height + spacing_y, spacing_y):
        offset = 0 if (y // spacing_y) % 2 == 0 else spacing_x // 2
        for x in range(-offset, src.width + spacing_x, spacing_x):
            draw.text((x, y), text, font=font, fill=(110, 20, 45, 72))
    result = Image.alpha_composite(src, overlay)
    out = BytesIO()
    if output_format.upper() == "PNG":
        result.save(out, format="PNG", optimize=True)
    else:
        result.convert("RGB").save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()