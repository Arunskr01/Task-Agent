import os
import pymupdf as fitz  # PyMuPDF
import pandas as pd

# ============ CONFIG ============
MODE = "single"  # "single" or "all"

PDF_PATH = r"D:\CodeBase\TestWorks\DigitalPDF\input\input_1.pdf"

OUTPUT_EXCEL_PATH = r"D:\CodeBase\TestWorks\DigitalPDF\output\input_1_Digital.xlsx"  # used when MODE = "single"
PAGE_NUMBER = 1                             # used when MODE = "single"

OUTPUT_DIR = r"D:\CodeBase\TestWorks\PDF\data"          # used when MODE = "all"

DPI = 400  # matches ~2479x3592 Azure OCR canvas size

TARGET_CANVAS_WIDTH = None   # set both to force an exact canvas size
TARGET_CANVAS_HEIGHT = None

MARGIN_PIXELS = 42  # top/bottom margin, matches Azure script
FONT_HEIGHT = 30    # page start/end label height
# =================================


def get_canvas_and_scale(page, dpi=DPI, target_canvas_width=None, target_canvas_height=None):
    # NOTE: page.rect already reflects the page's /Rotate value (its width/
    # height are swapped for 90/270-degree pages). That's correct and is
    # what we want the canvas to match.
    if target_canvas_width is not None and target_canvas_height is not None:
        canvas_width = int(target_canvas_width)
        canvas_height = int(target_canvas_height)
        scale_x = canvas_width / page.rect.width
        scale_y = canvas_height / page.rect.height
    else:
        zoom = dpi / 72.0
        canvas_width = round(page.rect.width * zoom)
        canvas_height = round(page.rect.height * zoom)
        scale_x = scale_y = zoom

    return canvas_width, canvas_height, scale_x, scale_y


def get_rotation_aware_words(page):
    """
    THE FIX: page.get_text("words") returns coordinates in the page's RAW,
    un-rotated coordinate space -- it ignores the page's /Rotate value.
    page.rect, however, DOES reflect /Rotate (width/height are swapped for
    90/270-degree pages).

    If a page has non-zero rotation and you scale the raw word coordinates
    against the rotated canvas size (as the original script did), you get
    exactly the corruption you were seeing: words that are visually on
    different lines collapsing into identical boxes, tiny "width" values
    paired with huge "height" values, block/line groupings that mix
    unrelated lines together, etc.

    This transforms every word box through the page's own rotation matrix
    so it lands in the SAME coordinate space as page.rect before anything
    else touches it. For unrotated pages (rotation == 0) this is a no-op.
    """
    words = page.get_text("words")

    if page.rotation == 0:
        return words

    mat = page.rotation_matrix  # raw/unrotated -> display (rotated) space
    fixed_words = []
    for x0, y0, x1, y1, text, block_no, line_no, word_no in words:
        p0 = fitz.Point(x0, y0) * mat
        p1 = fitz.Point(x1, y1) * mat
        nx0, nx1 = sorted((p0.x, p1.x))
        ny0, ny1 = sorted((p0.y, p1.y))
        fixed_words.append((nx0, ny0, nx1, ny1, text, block_no, line_no, word_no))

    return fixed_words


def get_line_box(line_words):
    x0 = min(w[0] for w in line_words)
    y0 = min(w[1] for w in line_words)
    x1 = max(w[2] for w in line_words)
    y1 = max(w[3] for w in line_words)
    return x0, y0, x1, y1


def extract_text_to_df(
    pdf_path,
    page_number=1,
    dpi=DPI,
    target_canvas_width=None,
    target_canvas_height=None,
    margin_pixels=MARGIN_PIXELS,
    font_height=FONT_HEIGHT
):
    try:
        doc = fitz.open(pdf_path)
        try:
            page_index = page_number - 1
            if page_index < 0 or page_index >= len(doc):
                raise ValueError(f"page_number {page_number} out of range (PDF has {len(doc)} pages)")

            page = doc[page_index]
            canvas_width, canvas_height, scale_x, scale_y = get_canvas_and_scale(
                page, dpi=dpi,
                target_canvas_width=target_canvas_width,
                target_canvas_height=target_canvas_height
            )

            # if page.rotation != 0:
            #     print(f"[info] page {page_number} has rotation={page.rotation}; "
            #           f"applying rotation-aware word extraction")

            words = get_rotation_aware_words(page)
            words.sort(key=lambda w: (w[5], w[6], w[0]))  # group by native block/line

            # group words into physical lines
            grouped_lines = []
            current_key = None
            current_line_words = []

            for word in words:
                key = (word[5], word[6])
                if current_key is None or key == current_key:
                    current_key = key
                    current_line_words.append(word)
                else:
                    grouped_lines.append({"words": current_line_words, "box": get_line_box(current_line_words)})
                    current_key = key
                    current_line_words = [word]

            if current_line_words:
                grouped_lines.append({"words": current_line_words, "box": get_line_box(current_line_words)})

            # re-sort into actual top-to-bottom reading order
            # (PyMuPDF's native block/line order is content-stream order, not visual order)
            grouped_lines.sort(key=lambda gl: (gl["box"][1], gl["box"][0]))

            # assign block/par/line numbers using Azure-style gap heuristic
            data_rows = []
            current_block_num = current_par_num = current_line_num = 1
            prev_box = None

            for line_data in grouped_lines:
                line_words = line_data["words"]
                x0, y0, x1, y1 = line_data["box"]

                line_left = x0 * scale_x
                line_top = y0 * scale_y
                line_right = x1 * scale_x
                line_bottom = y1 * scale_y
                line_height = max(1, line_bottom - line_top)

                if prev_box is not None:
                    p_left, p_top, p_right, p_bottom = prev_box
                    vertical_gap = line_top - p_bottom
                    horiz_overlap = not (line_right < p_left or line_left > p_right)

                    if not horiz_overlap and abs(line_top - p_top) > line_height:
                        current_block_num += 1
                        current_par_num = current_line_num = 1
                    elif vertical_gap > line_height * 1.5:
                        current_block_num += 1
                        current_par_num = current_line_num = 1
                    elif vertical_gap > line_height * 0.4:
                        current_par_num += 1
                        current_line_num = 1
                    else:
                        current_line_num += 1

                prev_box = (line_left, line_top, line_right, line_bottom)
                block_num, par_num, line_num = current_block_num, current_par_num, current_line_num

                for word_idx, word in enumerate(line_words):
                    wx0, wy0, wx1, wy1, text = word[0], word[1], word[2], word[3], word[4]
                    left = wx0 * scale_x
                    width = (wx1 - wx0) * scale_x

                    data_rows.append({
                        "block_num": block_num,
                        "par_num": par_num,
                        "line_num": line_num,
                        "word_num": word_idx + 1,
                        "left": left,
                        "top": line_top,
                        "width": width,
                        "height": line_height,
                        "conf": 100,
                        "text": text,
                        "canvas_width": canvas_width,
                        "canvas_height": canvas_height
                    })

            df = pd.DataFrame(data_rows)
            columns = ["block_num", "par_num", "line_num", "word_num", "left", "top",
                       "width", "height", "conf", "text", "canvas_width", "canvas_height"]

            new_canvas_height = canvas_height + 2 * margin_pixels

            if not df.empty:
                df["top"] = df["top"] + margin_pixels
                df["canvas_height"] = new_canvas_height
                result_df = df[columns]
            else:
                result_df = pd.DataFrame(columns=columns)

            page_start_row = pd.DataFrame([{
                "block_num": 0, "par_num": 1, "line_num": 1, "word_num": 1,
                "left": 10, "top": 5, "width": 300, "height": font_height,
                "conf": 100, "text": f"Page No {page_number} Starting",
                "canvas_width": canvas_width, "canvas_height": new_canvas_height
            }])
            page_end_row = pd.DataFrame([{
                "block_num": 999, "par_num": 1, "line_num": 1, "word_num": 1,
                "left": 10, "top": new_canvas_height - margin_pixels + 5,
                "width": 300, "height": font_height,
                "conf": 100, "text": f"Page No {page_number} Ending",
                "canvas_width": canvas_width, "canvas_height": new_canvas_height
            }])

            result_df = pd.concat([page_start_row, result_df, page_end_row], ignore_index=True)
            return result_df

        finally:
            doc.close()

    except Exception as e:
        raise Exception(f"Failed to extract text from PDF natively: {str(e)}")


def extract_pdf_all_pages(
    pdf_path,
    dpi=DPI,
    target_canvas_width=None,
    target_canvas_height=None,
    margin_pixels=MARGIN_PIXELS,
    font_height=FONT_HEIGHT
):
    """
    Extract all pages of a PDF to a list of DataFrames.

    Returns:
        list[pd.DataFrame]: One DataFrame per page.
    """
    doc = fitz.open(pdf_path)
    try:
        num_pages = len(doc)
    finally:
        doc.close()

    dataframes = []
    for page_number in range(1, num_pages + 1):
        df = extract_text_to_df(
            pdf_path=pdf_path,
            page_number=page_number,
            dpi=dpi,
            target_canvas_width=target_canvas_width,
            target_canvas_height=target_canvas_height,
            margin_pixels=margin_pixels,
            font_height=font_height
        )
        dataframes.append(df)

    return dataframes


if __name__ == "__main__":
    if MODE == "single":
        df = extract_text_to_df(
            pdf_path=PDF_PATH,
            page_number=PAGE_NUMBER,
            dpi=DPI,
            target_canvas_width=TARGET_CANVAS_WIDTH,
            target_canvas_height=TARGET_CANVAS_HEIGHT,
            margin_pixels=MARGIN_PIXELS,
            font_height=FONT_HEIGHT
        )
        df.to_excel(OUTPUT_EXCEL_PATH, index=False)
        # print(f"Saved to {OUTPUT_EXCEL_PATH}")

    elif MODE == "all":
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        pdf_name = os.path.splitext(os.path.basename(PDF_PATH))[0]
        dataframes = extract_pdf_all_pages(
            pdf_path=PDF_PATH,
            dpi=DPI,
            target_canvas_width=TARGET_CANVAS_WIDTH,
            target_canvas_height=TARGET_CANVAS_HEIGHT,
            margin_pixels=MARGIN_PIXELS,
            font_height=FONT_HEIGHT
        )
        for i, df in enumerate(dataframes, start=1):
            output_path = os.path.join(OUTPUT_DIR, f"{pdf_name}_pg{i}_extracted.xlsx")
            df.to_excel(output_path, index=False)
        # print(f"Saved {len(dataframes)} files to {OUTPUT_DIR}")

    else:
        raise ValueError(f"Unknown MODE {MODE!r}: use 'single' or 'all'")