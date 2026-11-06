import pymupdf as fitz  # PyMuPDF
import os
import base64
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG: Number of page images to send to GPT for document structure understanding ---
# Set to 0 to disable sending images. Set higher to give GPT more visual context (increases token usage).
IMAGE_PAGES_TO_SEND = 0

import fitz

import pdfplumber

def extract_text_from_pdf(pdf_path):
    """
    Extracts text from a PDF while maintaining the visual layout.
    Returns the extracted text as a single string variable.
    """
    extracted_text = []
    
    # Open the PDF
    with pdfplumber.open(pdf_path) as pdf:
        # Iterate through all the pages in the document
        for page in pdf.pages:
            # extract_text(layout=True) preserves the visual columns and spacing
            text = page.extract_text(layout=True)
            
            if text:
                extracted_text.append(text)
                # Adds a visual separator between pages (optional, but helpful for multi-page invoices)
                extracted_text.append("\n" + "="*40 + "\n") 
                
    # Join all the page texts together into one massive string
    full_text_string = "".join(extracted_text)
    
    return full_text_string


def _get_page_images_base64(pdf_path, images_folder=None):
    """Get base64-encoded page images for the first IMAGE_PAGES_TO_SEND pages.
    Uses cached images from images_folder if available, otherwise renders from PDF."""
    page_images = []
    num_pages = max(0, IMAGE_PAGES_TO_SEND)
    if num_pages == 0:
        return page_images
    
    # Try to use cached images from the pipeline (already rendered at 3x zoom)
    if images_folder and os.path.isdir(images_folder):
        image_files = sorted([
            f for f in os.listdir(images_folder)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff'))
        ])
        for img_file in image_files[:num_pages]:
            img_path = os.path.join(images_folder, img_file)
            with open(img_path, "rb") as f:
                page_images.append(base64.b64encode(f.read()).decode("utf-8"))
        if page_images:
            # print(f"  Using {len(page_images)} cached image(s) from pipeline.")
            return page_images
    
    # Fallback: render pages directly from the PDF
    try:
        doc = fitz.open(pdf_path)
        pages_to_render = min(num_pages, len(doc))
        for page_num in range(pages_to_render):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for reasonable size
            img_bytes = pix.tobytes("png")
            page_images.append(base64.b64encode(img_bytes).decode("utf-8"))
        doc.close()
        # print(f"  Rendered {len(page_images)} page image(s) from PDF.")
    except Exception as e:
        print(f"  Warning: Could not generate page images: {e}")
    
    return page_images

