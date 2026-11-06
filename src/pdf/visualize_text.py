import pandas as pd
import pymupdf as fitz  # PyMuPDF
import statistics
import os
from bidi.algorithm import get_display

_FONT_CHAIN = [
    ("segoeui.ttf",  "Latin, Arabic, Hebrew, Greek, Cyrillic, Georgian, Vietnamese"),
    ("Nirmala.ttc",  "Hindi, Tamil, Bengali, and other Indic scripts"),
    ("msyh.ttc",     "Chinese, Japanese"),
    ("malgun.ttf",   "Korean"),
    ("tahoma.ttf",   "Thai"),
]

_FONTS_DIR = r"C:\Windows\Fonts"


def _load_font_chain():
    """Load all available fonts from the fallback chain.
    Returns a list of fitz.Font objects (primary font first)."""
    chain = []
    for basename, _desc in _FONT_CHAIN:
        path = os.path.join(_FONTS_DIR, basename)
        if os.path.exists(path):
            try:
                chain.append(fitz.Font(fontfile=path))
            except Exception:
                pass  # Skip fonts that fail to load
    if not chain:
        # Absolute fallback: use PyMuPDF built-in (Latin only)
        chain.append(fitz.Font("helv"))
    return chain


def _select_font(text, font_chain):
    """Pick the best font for the given text string.
    Returns the first font in the chain that has glyphs for every
    non-whitespace character.  Falls back to the primary font."""
    chars = [ord(ch) for ch in text if not ch.isspace()]
    if not chars:
        return font_chain[0]

    for font in font_chain:
        if all(font.has_glyph(cp) for cp in chars):
            return font

    # No single font covers everything — return primary as best-effort
    return font_chain[0]


def _bidi_reorder(text):
    """Apply the Unicode Bidirectional Algorithm to reorder RTL text.
    PyMuPDF places characters left-to-right; this converts logical order
    to visual order so Arabic/Hebrew text renders correctly."""
    try:
        return get_display(text)
    except Exception:
        return text


def visualize_text_high_res(excel_path, output_pdf_path):
    try:
        df = pd.read_excel(excel_path)
        
        # Calculate canvas size
        scale_factor = 3.0
        if 'canvas_width' in df.columns:
            canvas_width = float(df['canvas_width'].iloc[0]) / scale_factor
            canvas_height = float(df['canvas_height'].iloc[0]) / scale_factor
        else:
            # Fallback if canvas width wasn't saved
            canvas_width = float((df['left'] + df['width']).max() + 50) / scale_factor
            canvas_height = float((df['top'] + df['height']).max() + 50) / scale_factor
            
        # Create a new native PDF document
        doc = fitz.open()
        
        # Casting to native python float is required for PyMuPDF C++ bindings
        page = doc.new_page(width=canvas_width, height=canvas_height)

        # Load the multilingual font chain
        font_chain = _load_font_chain()
        primary_font = font_chain[0]

        # Create a TextWriter for this page — required for custom font rendering
        tw = fitz.TextWriter(page.rect)
        
        if 'block_num' in df.columns:
            # Check for associated tables file
            tables_excel_path = excel_path.replace('_extracted.xlsx', '_tables.xlsx')
            if os.path.exists(tables_excel_path):
                df_tables = pd.read_excel(tables_excel_path)
                if not df_tables.empty:
                    # Draw table cells
                    for _, cell in df_tables.iterrows():
                        left = float(cell['left']) / scale_factor
                        top = float(cell['top']) / scale_factor
                        width = float(cell['width']) / scale_factor
                        height = float(cell['height']) / scale_factor
                        # PyMuPDF expects a Rect object for drawing rectangles
                        rect = fitz.Rect(left, top, left + width, top + height)
                        # Draw black border with 1px width
                        page.draw_rect(rect, color=(0, 0, 0), width=0.5)

            # Sort chronologically by logical page stream (Z-order)
            df = df.sort_values(by=['block_num', 'par_num', 'line_num', 'word_num'])
            
            # Step 1: Pre-calculate the exact median font size per block using horizontal geometry
            block_font_sizes = {}
            for block_id, block_df in df.groupby('block_num'):
                line_sizes = []
                for _, line_group in block_df.groupby(['par_num', 'line_num']):
                    line_text = " ".join([str(x) for x in line_group['text'].tolist()]).strip()
                    if not line_text:
                        continue
                    
                    # Reorder RTL text for correct visual rendering
                    line_text = _bidi_reorder(line_text)
                        
                    min_x = float(line_group['left'].min()) / scale_factor
                    max_r = float((line_group['left'] + line_group['width']).max()) / scale_factor
                    target_width = max_r - min_x
                    
                    # Use the best-matching font's own metrics for accurate measurement
                    font = _select_font(line_text, font_chain)
                    unit_length = font.text_length(line_text, fontsize=1.0)
                    if unit_length > 0:
                        # Estimate required font size to perfectly fit this space horizontally
                        line_sizes.append(target_width / unit_length)
                
                if line_sizes:
                    block_font_sizes[block_id] = statistics.median(line_sizes)
                else:
                    block_font_sizes[block_id] = 12.0 # fallback
                    
            # Step 2: Draw the text using the unified paragraph sizes
            groups = df.groupby(['block_num', 'par_num', 'line_num'], sort=False)
            
            for _, group in groups:
                line_text = " ".join([str(x) for x in group['text'].tolist()]).strip()
                if not line_text:
                    continue
                
                # Reorder RTL text for correct visual rendering
                line_text = _bidi_reorder(line_text)
                
                first_word = group.iloc[0]
                block_id = first_word['block_num']
                
                x0 = float(first_word['left']) / scale_factor
                y0 = float(group['top'].min()) / scale_factor
                
                # Select the best font for this specific line
                font = _select_font(line_text, font_chain)
                
                # Base paragraph font size
                base_fontsize = block_font_sizes.get(block_id, 12.0)
                
                # Strict cutoff: Ensure it mathematically cannot exceed the canvas margins
                unit_length = font.text_length(line_text, fontsize=1.0)
                if unit_length > 0:
                    max_allowed = (canvas_width - x0 - 5) / unit_length
                    fontsize = min(base_fontsize, max_allowed)
                else:
                    fontsize = base_fontsize
                
                # PDF text insertions usually start from the bottom-left baseline
                baseline_offset = fontsize * 0.8
                point = fitz.Point(x0, y0 + baseline_offset)
                
                tw.append(point, line_text, font=font, fontsize=fontsize)
                
        else:
            # Fallback for old data without column structure
            for _, row in df.iterrows():
                text = str(row['text']).strip()
                if not text:
                    continue
                
                # Reorder RTL text for correct visual rendering
                text = _bidi_reorder(text)
                x0 = float(row['left']) / scale_factor
                y0 = float(row['top']) / scale_factor
                h = float(row['height']) / scale_factor
                
                font = _select_font(text, font_chain)
                unit_length = font.text_length(text, fontsize=1.0)
                if unit_length > 0:
                    max_allowed = (canvas_width - x0 - 5) / unit_length
                    fontsize = min(h, max_allowed)
                else:
                    fontsize = h

                baseline_offset = fontsize * 0.8
                point = fitz.Point(x0, y0 + baseline_offset)
                tw.append(point, text, font=font, fontsize=fontsize)
        
        # Commit all text to the page in one operation
        tw.write_text(page)
                
        doc.save(output_pdf_path)
        doc.close()
        
        # print(f"Plotted real PDF text saved to {output_pdf_path}")
        
    except Exception as e:
        # print(f"Error visualizing text from {excel_path}.")
        raise Exception(f"Failed to visualize text: {str(e)}")

if __name__ == "__main__":
    excel_file = r"D:\New folder\DocuZone\Excel\10PagePDF_pg1_extracted.xlsx"
    output_file = r"D:\New folder\DocuZone\Ploted\recreated_canvas.pdf"
    
    visualize_text_high_res(excel_file, output_file)