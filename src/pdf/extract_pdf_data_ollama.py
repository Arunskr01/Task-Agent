import pymupdf as fitz  # PyMuPDF
import requests
import json
import os
import time
import base64
import pandas as pd

# --- CONFIG: Number of page images to send to Ollama for document structure understanding ---
# Set to 0 to disable sending images. Set higher to give the model more visual context.
IMAGE_PAGES_TO_SEND = 3

# --- Ollama Configuration ---
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "mistral-large-3:675b-cloud"
OLLAMA_ENDPOINT = f"{OLLAMA_BASE_URL}/api/chat"


def extract_text_from_pdf(pdf_path):
    """Reads the PDF file and extracts all text using PyMuPDF."""
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            text += page.get_text()
    except Exception as e:
        print(f"Error reading PDF: {e}")
    return text


def extract_data_with_ollama(pdf_text, user_prompt, page_images=None):
    """Sends the PDF text and user prompt to Ollama to extract data as JSON.
    Optionally includes page images (base64) for document structure understanding."""

    # System prompt strictly instructing the model to return JSON
    system_prompt = (
        "You are a HIGH-PRECISION lossless document data extraction engine."
        "Task: Extract COMPLETE structured data from provided PDF TEXT."
        ""
        "CRITICAL:"
        "This is FULL DOCUMENT extraction."
        "Process until FINAL PAGE and FINAL ROW."
        "Never stop early due to long output."
        "Completeness is mandatory."
        ""
        "IMAGES:"
        "Images are layout reference only. They do not represent the number of pages or rows to extract."
        "Do NOT extract data from images."
        "Use ONLY provided PDF TEXT."
        ""
        "GLOBAL RULES:"
        "1. Process pages sequentially from first to last."
        "2. Assume table continues unless clear new section or document end."
        "3. Extract EVERY visible row."
        "4. Similar/identical rows are still separate."
        "5. Never merge, group, summarize or deduplicate."
        "6. Continue tables across pages."
        "7. Reconstruct rows split across lines/pages into ONE row."
        "8. Missing requested field → return null. Never guess."
        "9. If unsure more rows exist → continue extraction."
        "10. Stop ONLY after final footer or termination text."
        "11. Before output internally verify:"
        "- All pages processed."
        "- No rows skipped."
        "- Continuations preserved."
        "- No duplicates removed."
        ""
        "HEADER EXTRACTION:"
        "Extract ONLY headers requested in user prompt."
        "Ignore page numbers, footers, legal text."
        "Header values may be next to or below label."
        "Repeat header values per page only if different."
        ""
        "TABLE EXTRACTION:"
        "Detect ALL tables per page."
        "Identify headers despite inconsistent formatting."
        "Extract rows until table end, new section, or document end."
        "If no table → \"Table\": null."
        ""
        "OUTPUT:"
        "Return STRICT valid JSON only."
        "No explanation, summary, truncation, or row reduction."
        ""
        "FINAL CONDITION:"
        "Task completes ONLY after ALL rows from ALL pages are extracted."
        ""
        "OUTPUT FORMAT:"
        "{"
        "\"Pages\":["
        "{"
        "\"Headers\":{},"
        "\"Table\":[{}]"
        "}"
        "]"
        "}"
        ""
    )

    # Build the user message text
    user_text = f"User Prompt: {user_prompt}\n\nDocument Text:\n{pdf_text}"

    # Build messages for Ollama API
    messages = [
        {"role": "system", "content": system_prompt},
    ]

    # Ollama supports images via the "images" field in a message (list of base64 strings)
    if page_images:
        messages.append({
            "role": "user",
            "content": user_text,
            "images": page_images  # List of base64-encoded image strings
        })
    else:
        messages.append({
            "role": "user",
            "content": user_text
        })

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "format": "json",   # Forces the model to return valid JSON
        "stream": False,     # Get the complete response at once
        "options": {
            "temperature": 0,          # Deterministic output for consistent extraction
            "num_ctx": 32768,          # Large context window for long documents
        }
    }

    try:
        response = requests.post(OLLAMA_ENDPOINT, json=payload, timeout=600)

        if response.status_code == 200:
            result = response.json()
            content = result.get("message", {}).get("content", None)
            if content:
                # Strip markdown code fences if the model wraps output in ```json ... ```
                content = content.strip()
                if content.startswith("```"):
                    # Remove opening fence (```json or ```)
                    first_newline = content.index("\n") if "\n" in content else len(content)
                    content = content[first_newline + 1:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
            return content
        else:
            print(f"Error from Ollama API: {response.status_code}")
            print(response.text)
            return None
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to Ollama. Make sure Ollama is running (ollama serve).")
        return None
    except requests.exceptions.Timeout:
        print("Error: Ollama request timed out. The document may be too large.")
        return None
    except Exception as e:
        print(f"Error communicating with Ollama: {e}")
        return None


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
    except Exception as e:
        print(f"  Warning: Could not generate page images: {e}")

    return page_images


def main(pdf_path, output_folder, json_output_folder, user_prompt, images_folder=None):
    print("--- Using AI Extraction (Ollama) ---")
    filename = os.path.basename(pdf_path)

    # Remove quotes if dragged and dropped in terminal
    if pdf_path.startswith('"') and pdf_path.endswith('"'):
        pdf_path = pdf_path[1:-1]

    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return

    output_json_path = os.path.join(json_output_folder, f"{os.path.splitext(filename)[0]}.json")
    output_excel = os.path.join(output_folder, f"{os.path.splitext(filename)[0]}.xlsx")

    # Prepare page images for Ollama visual context
    page_images = _get_page_images_base64(pdf_path, images_folder)

    # Extract text from PDF
    pdf_text = extract_text_from_pdf(pdf_path)

    if not pdf_text.strip():
        print("No text could be extracted from the PDF. It might be an image-only PDF.")
        return

    # Send to Ollama for extraction
    json_output_string = extract_data_with_ollama(pdf_text, user_prompt, page_images=page_images)

    if json_output_string:
        try:
            # Parse and re-dump to ensure it's formatted nicely
            parsed_json = json.loads(json_output_string)
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(parsed_json, f, indent=4)

            data = json.load(open(output_json_path, "r"))
            all_rows = []
            count = 0
            for page in data["Pages"]:
                if count == 0:
                    header1 = page["Headers"]
                    FOIs = pd.DataFrame(list(header1.items()), columns=['FOI', 'Value'])
                    count += 1
                table_rows = page["Table"]
                if table_rows:
                    all_rows.extend(table_rows)

            FOTs = pd.DataFrame(all_rows)

            # Write both sheets
            with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
                FOIs.to_excel(writer, index=False, sheet_name="FOIs")
                FOTs.to_excel(writer, index=False, sheet_name="Table")
            return data
        except json.JSONDecodeError:
            print("Warning: Ollama did not return valid JSON. Saving raw output instead.")
            with open(output_json_path, 'w', encoding='utf-8') as f:
                f.write(json_output_string)
            print(f"Raw output saved to: {os.path.abspath(output_json_path)}")
            return None
    return None


if __name__ == "__main__":
    pass
