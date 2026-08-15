from io import BytesIO
from datetime import datetime, timezone
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color
from PIL import Image, ImageDraw, ImageFont


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


def _font(size: int):
    # Keep the runtime portable: default bitmap font is sufficient for the
    # ASCII trace string (email + student ID + timestamp).
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
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
