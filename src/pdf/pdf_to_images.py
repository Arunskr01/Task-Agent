import os
import pymupdf as fitz

def convert_pdf_to_images(pdf_path, output_folder):
    try:
        # Create output folder if it doesn't exist
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            print(f"Created folder: {output_folder}")

        # Get the base name of the PDF file to use in image names
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        
        # print(f"Converting {pdf_path}...")
        
        # Open the PDF file
        pdf_document = fitz.open(pdf_path)
        
        # Iterate through each page
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            
            # Render page to an image (pixmap)
            # Increase resolution to 300 DPI for best OCR quality (300 / 72 = ~4.166)
            matrix = fitz.Matrix(400/72, 400/72)
            pix = page.get_pixmap(matrix=matrix)
            
            # Define image path
            image_name = f"{pdf_name}_pg{page_num + 1}.png"
            image_path = os.path.join(output_folder, image_name)
            
            # Save the image
            pix.save(image_path)
            # print(f"Saved: {image_path}")
            
        # print(f"Successfully converted {pdf_path} to {len(pdf_document)} images.")
        
    except Exception as e:
        print(f"Error converting {pdf_path}.")
        raise Exception(f"Failed to convert PDF to images: {str(e)}")

if __name__ == "__main__":
    # Output folder name
    output_folder = r"D:\New folder\DocuZone\Images"
    pdf_path = r"D:\AutomationAnywhere\Sample PDF\Invoice_1.pdf"
    convert_pdf_to_images(pdf_path, output_folder)
