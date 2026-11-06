import requests
import time
import base64
import xml.etree.ElementTree as ET
import os
import pandas as pd
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# Your credentials
APP_ID = os.getenv("ABBYY_APPID")
PASSWORD = os.getenv("ABBYY_PASSWORD")

credentials = base64.b64encode(f"{APP_ID}:{PASSWORD}".encode()).decode()
headers = {"Authorization": f"Basic {credentials}"}

BASE_URL = "https://cloud.ocrsdk.com"


def parse_task_response(response):
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    body = response.text.strip()

    if "application/json" in content_type or body.startswith("{"):
        return response.json()

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError(f"Unexpected ABBYY response format: {exc}\n{body[:500]}")

    task = root.find(".//task")
    if task is None:
        raise ValueError(f"No <task> element found in ABBYY response:\n{body[:500]}")

    return {
        "taskId": task.attrib.get("id"),
        "status": task.attrib.get("status"),
        "resultUrl": task.attrib.get("resultUrl"),
    }


def submit_image(image_path):
    url = f"{BASE_URL}/processImage?exportFormat=alto&language=English,Arabic" 
    request_headers = headers.copy()
    request_headers["Content-Type"] = "image/png"
    with open(image_path, "rb") as f:
        response = requests.post(url, headers=request_headers, data=f)
    data = parse_task_response(response)
    if not data.get("taskId"):
        raise ValueError(f"Unable to parse task ID from ABBYY response: {response.text}")
    return data["taskId"]


def wait_for_result(task_id):
    url = f"{BASE_URL}/getTaskStatus?taskId={task_id}"
    while True:
        response = requests.get(url, headers=headers)
        data = parse_task_response(response)
        status = data.get("status")
        # print(f"Status: {status}")
        if status == "Completed":
            return data.get("resultUrl")
        if status == "ProcessingFailed":
            raise Exception("OCR failed!")
        if status is None:
            raise Exception("Unexpected ABBYY task status response")
        time.sleep(2)


def download_result(result_url):
    response = requests.get(result_url)
    if response.status_code in (401, 403):
        response = requests.get(result_url, headers=headers)
    response.raise_for_status()
    return response.text


def parse_alto_to_rows(alto_xml):
    """
    Parse ALTO XML and return rows matching the format:
    block_num, par_num, line_num, word_num, left, top, width, height, conf, text, canvas_width, canvas_height
    """
    root = ET.fromstring(alto_xml)

    # Detect namespace
    ns_map = {}
    raw_tag = root.tag
    if raw_tag.startswith("{"):
        ns_uri = raw_tag[1:raw_tag.index("}")]
        ns_map = {"alto": ns_uri}
        def tag(name): return f"{{{ns_uri}}}{name}"
    else:
        def tag(name): return name

    # Get page dimensions
    page = root.find(f".//{tag('Page')}")
    canvas_width = int(page.attrib.get("WIDTH", 0)) if page is not None else 0
    canvas_height = int(page.attrib.get("HEIGHT", 0)) if page is not None else 0

    rows = []
    block_num = 0

    for text_block in root.iter(tag("TextBlock")):
        block_num += 1
        par_num = 1  # ALTO doesn't have paragraph concept; use 1 per block

        for line_num, text_line in enumerate(text_block.iter(tag("TextLine")), start=1):
            for word_num, string_el in enumerate(text_line.iter(tag("String")), start=1):
                text = string_el.attrib.get("CONTENT", "")
                left = int(string_el.attrib.get("HPOS", 0))
                top = int(string_el.attrib.get("VPOS", 0))
                width = int(string_el.attrib.get("WIDTH", 0))
                height = int(string_el.attrib.get("HEIGHT", 0))
                conf_raw = string_el.attrib.get("WC", "0")
                # WC is 0–1 in ALTO; multiply by 100 to match Tesseract-style confidence
                conf = float(conf_raw) * 100

                rows.append({
                    "block_num": block_num,
                    "par_num": par_num,
                    "line_num": line_num,
                    "word_num": word_num,
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                    "conf": conf,
                    "text": text,
                    "canvas_width": canvas_width,
                    "canvas_height": canvas_height,
                })

    return rows


def extract_text_to_excel(image_path, output_excel_path, page_number=1):
    try:
        # Get image size to maintain compatibility with visualize_text formatting
        img = Image.open(image_path)
        canvas_width, canvas_height = img.size
        
        task_id = submit_image(image_path)
        result_url = wait_for_result(task_id)
        alto_xml = download_result(result_url)
        
        data_rows = parse_alto_to_rows(alto_xml)
        
        df = pd.DataFrame(data_rows)
        
        # Select target columns matching Tesseract structured output
        columns = ['block_num', 'par_num', 'line_num', 'word_num', 'left', 'top', 'width', 'height', 'conf', 'text', 'canvas_width', 'canvas_height']
        
        # --- Add 0.5 cm margin at top and bottom for page numbers ---
        # At 3x zoom (~216 DPI), 0.5 cm ≈ 42 pixels
        margin_pixels = 42
        new_canvas_height = canvas_height + 2 * margin_pixels
        
        if not df.empty:
            # Shift all existing content down by margin_pixels to make room for top margin
            df['top'] = df['top'] + margin_pixels
            # Update canvas dimensions in all rows
            df['canvas_height'] = new_canvas_height
            result_df = df[columns]
        else:
            result_df = pd.DataFrame(columns=columns)
            
        # Create page number label rows
        font_height = 30  # approximate font height in pixels at 3x scale
        page_start_row = pd.DataFrame([{
            'block_num': 0, 'par_num': 1, 'line_num': 1, 'word_num': 1,
            'left': 10, 'top': 5, 'width': 300, 'height': font_height,
            'conf': 100, 'text': f'Page No {page_number} Starting',
            'canvas_width': canvas_width, 'canvas_height': new_canvas_height
        }])
        page_end_row = pd.DataFrame([{
            'block_num': 999, 'par_num': 1, 'line_num': 1, 'word_num': 1,
            'left': 10, 'top': new_canvas_height - margin_pixels + 5,
            'width': 300, 'height': font_height,
            'conf': 100, 'text': f'Page No {page_number} Ending',
            'canvas_width': canvas_width, 'canvas_height': new_canvas_height
        }])
        
        # Combine: page start label + content + page end label
        result_df = pd.concat([page_start_row, result_df, page_end_row], ignore_index=True)
            
        # Save explicitly mapped structure to Excel
        result_df.to_excel(output_excel_path, index=False)
        
    except Exception as e:
        raise Exception(f"Failed to extract text from image using ABBYY: {str(e)}")

# Remove __main__ execution here to prevent unintended static testing bugs for images vs PDF conversions