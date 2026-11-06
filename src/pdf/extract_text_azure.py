import os
import time
import pandas as pd
from PIL import Image
from msrest.authentication import CognitiveServicesCredentials
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes

def extract_text_to_df(image_path, page_number=1, ocr_key=None, ocr_endpoint=None):
    """
    Extracts text from an image via Azure Computer Vision OCR.

    Returns a pandas DataFrame with the word-level coordinate table.

    ocr_key and ocr_endpoint are required and are fetched from the
    OCR_Config database table by the caller (CoreEngine / CLI / main).
    """
    
    if not ocr_key or not ocr_endpoint:
        raise ValueError(
            "ocr_key and ocr_endpoint must be provided. "
            "They are fetched from the OCR_Config table in the database."
        )
    client = ComputerVisionClient(ocr_endpoint, CognitiveServicesCredentials(ocr_key))

    try:
        # Get image size to maintain compatibility with visualize_text formatting
        img = Image.open(image_path)
        canvas_width, canvas_height = img.size
        
        # Call Azure Read API
        with open(image_path, "rb") as image_stream:
            read_response = client.read_in_stream(image_stream, raw=True)
            
        # Get operation ID to poll for result
        read_operation_location = read_response.headers["Operation-Location"]
        operation_id = read_operation_location.split("/")[-1]
        
        # Poll for result
        while True:
            read_result = client.get_read_result(operation_id)
            if read_result.status not in ['notStarted', 'running']:
                break
            time.sleep(1)
            
        data_rows = []
        
        if read_result.status == OperationStatusCodes.succeeded:
            for text_result in read_result.analyze_result.read_results:
                current_block_num = 1
                current_par_num = 1
                current_line_num = 1
                prev_box = None
                
                for line_idx, line in enumerate(text_result.lines):
                    # Calculate basic bounding box for the line
                    l_box = line.bounding_box
                    line_left = min(l_box[0], l_box[6])
                    line_top = min(l_box[1], l_box[3])
                    line_right = max(l_box[2], l_box[4])
                    line_bottom = max(l_box[5], l_box[7])
                    line_height = max(1, line_bottom - line_top) # Avoid zero height
                    
                    if prev_box is not None:
                        p_left, p_top, p_right, p_bottom = prev_box
                        vertical_gap = line_top - p_bottom
                        
                        # Check horizontal overlap
                        horiz_overlap = not (line_right < p_left or line_left > p_right)
                        
                        # Heuristic grouping rules for blocks and paragraphs:
                        # 1. New Block: Large vertical gap OR no horizontal overlap (e.g. new column)
                        # 2. New Paragraph: Moderate vertical gap
                        # 3. Same Paragraph: Small vertical gap
                        if not horiz_overlap and abs(line_top - p_top) > line_height:
                            current_block_num = current_block_num + 1
                            current_par_num = 1
                            current_line_num = 1
                        elif vertical_gap > line_height * 1.5:
                            current_block_num = current_block_num + 1
                            current_par_num = 1
                            current_line_num = 1
                        elif vertical_gap > line_height * 0.4:
                            current_par_num = current_par_num + 1
                            current_line_num = 1
                        else:
                            current_line_num = current_line_num + 1
                            
                    prev_box = (line_left, line_top, line_right, line_bottom)
                    
                    block_num = current_block_num
                    par_num = current_par_num
                    line_num = current_line_num
                    
                    for word_idx, word in enumerate(line.words):
                        # Azure bounding box is a 8-point polygon: [x0, y0, x1, y1, x2, y2, x3, y3]
                        # We convert it to standard Box format [left, top, width, height]
                        box = word.bounding_box
                        left = min(box[0], box[6])
                        top = min(box[1], box[3])
                        width = max(box[2], box[4]) - left
                        height = max(box[5], box[7]) - top
                        
                        data_rows.append({
                            'block_num': block_num,
                            'par_num': par_num,
                            'line_num': line_num,
                            'word_num': word_idx + 1,
                            'left': left,
                            'top': top,
                            'width': width,
                            'height': height,
                            'conf': word.confidence * 100 if word.confidence else 100, # Tesseract scaled is 0-100
                            'text': word.text,
                            'canvas_width': canvas_width,
                            'canvas_height': canvas_height
                        })
                        
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
            # print(f"Warning: No text detected in {image_path}")
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
            
        return result_df

    except Exception as e:
        raise Exception(f"Failed to extract text from image using Azure: {str(e)}")

# Remove __main__ execution here to prevent unintended static testing bugs for images vs PDF conversions
