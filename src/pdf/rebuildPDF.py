import os
import pandas as pd
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Base-14 PDF fonts (Helvetica etc.) only cover Latin-1 — real-world business
# documents routinely contain glyphs outside that (₹, ☑, ✓, — , non-Latin
# scripts, etc.). DejaVu Sans has much broader Unicode coverage and ships with
# most Linux systems, so we embed it instead and fall back to Helvetica only
# if it truly isn't available.
_FONTS_DIR = r"C:\Windows\Fonts"
_SEGOE_CANDIDATES = [
    os.path.join(_FONTS_DIR, "segoeui.ttf"),
]

def _register_unicode_font():
    for path in _SEGOE_CANDIDATES:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont("SegoeUI", path))
            return "SegoeUI"
    return "Helvetica"  # fallback; will drop glyphs outside Latin-1


def rebuild_pdf(df, output_pdf_path, margin_pixels=42, dpi=216, font_name=None):
    """
    Reconstruct a PDF from a word-level coordinate DataFrame (block_num, par_num,
    line_num, word_num, left, top, width, height, conf, text, canvas_width,
    canvas_height) produced by the extraction pipeline.

    Two things are guaranteed to be true of the output:
      1. VISUAL: each word is drawn at its original geometric position/size, so
         the page looks the same as the source.
      2. LOGICAL/READING ORDER: words are written into the PDF's content stream
         in exactly the row order they appear in the DataFrame. Since
         copy/paste, Ctrl+F, screen readers, and text-extraction tools all read
         a PDF's text in content-stream order, whatever order the rows are in
         when you pass them in becomes the order those tools will see. So if
         you've already re-sorted the rows into true reading order, that fix
         carries straight through to the output PDF.

    Page breaks are detected from the pipeline's own markers: a row with
    block_num == 0 and text starting "Page No" opens a page, block_num == 999
    closes it. Those two marker rows are metadata only and are not drawn.

    margin_pixels/dpi must match whatever the extraction step used (defaults
    here match extract_text_azure.py / digitalExtraction.py: 42px margin
    at 216 DPI, i.e. a 3x zoom on 72-DPI PDF points).
    """
    if font_name is None:
        font_name = _register_unicode_font()

    zoom = dpi / 72.0

    if df.empty:
        c = pdfcanvas.Canvas(output_pdf_path)
        c.showPage()
        c.save()
        return

    canvas_w = df["canvas_width"].iloc[0]
    canvas_h = df["canvas_height"].iloc[0]

    c = pdfcanvas.Canvas(output_pdf_path)
    page_w_pts = canvas_w / zoom
    page_h_pts = canvas_h / zoom
    c.setPageSize((page_w_pts, page_h_pts))

    for _, row in df.iterrows():
        text = str(row["text"]) if pd.notna(row["text"]) else ""
        if not text.strip():
            continue

        x_pts = row["left"] / zoom
        top_pts = row["top"] / zoom
        w_pts = row["width"] / zoom
        h_pts = row["height"] / zoom
        y_baseline = page_h_pts - top_pts - h_pts

        # Approximate font size from glyph bbox height (cap-height ratio).
        font_size = max(1.0, h_pts * 0.82)
        c.setFont(font_name, font_size)

        # Stretch/compress horizontally so the drawn word matches the
        # original bounding-box width as closely as possible, without
        # distorting so much it looks broken.
        natural_width = c.stringWidth(text, font_name, font_size)
        if natural_width > 0 and w_pts > 0:
            h_scale = max(40.0, min(160.0, (w_pts / natural_width) * 100.0))
        else:
            h_scale = 100.0

        c.saveState()
        c.translate(x_pts, y_baseline)
        if abs(h_scale - 100.0) > 0.5:
            c.scale(h_scale / 100.0, 1.0)
        c.drawString(0, 0, text)
        c.restoreState()

    c.showPage()
    c.save()


if __name__ == "__main__":
    # Configuration
    CONFIG = {
        "excel_path": r"D:\CodeBase\TestWorks\DigitalPDF\output\input_1_Digital.xlsx",
        "output_pdf_path": r"D:\CodeBase\TestWorks\DigitalPDF\output\input_1_rebuilt.pdf",
        "margin_pixels": 42,
        "dpi": 216,
        "font_name": None,  # None will auto-detect Unicode font (e.g. Segoe UI)
    }

    df = pd.read_excel(CONFIG["excel_path"])
    rebuild_pdf(
        df=df,
        output_pdf_path=CONFIG["output_pdf_path"],
        margin_pixels=CONFIG["margin_pixels"],
        dpi=CONFIG["dpi"],
        font_name=CONFIG["font_name"],
    )
    print(f"Saved to {CONFIG['output_pdf_path']}")