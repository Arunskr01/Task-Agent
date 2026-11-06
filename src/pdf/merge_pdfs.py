import os
import shutil
import re
from PyPDF2 import PdfMerger

def merge_pdfs(input_folder, output_folder, input_file_name):
    # Check if input directory exists
    if not os.path.exists(input_folder):
        print(f"Error: The input folder '{input_folder}' does not exist.")
        return

    # Create output directory if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"Created output folder: {output_folder}")

    # Get list of PDF files and sort them numerically by page number (e.g. pg2 before pg10)
    pdf_files = [f for f in os.listdir(input_folder) if f.lower().endswith('.pdf')]
    
    def extract_page_number(filename):
        # Look for '_pg' followed by any digits
        match = re.search(r'_pg(\d+)', filename)
        if match:
            return int(match.group(1))
        return 0 # Default fallback if pattern isn't found
        
    pdf_files.sort(key=extract_page_number)

    if not pdf_files:
        print("No PDF files found in the input folder.")
        return

    # If there is only a single PDF, copy it
    if len(pdf_files) == 1:
        filename = pdf_files[0]
        source_path = os.path.join(input_folder, filename)
        destination_path = os.path.join(output_folder, f"{os.path.splitext(input_file_name)[0]}_Converted.pdf")
        
        # print(f"Single PDF found ({filename}). Copying to output folder...")
        shutil.copy2(source_path, destination_path)
        # print(f"Successfully copied to: {destination_path}")

    # If there are multiple PDFs, merge them
    else:
        # print(f"Found {len(pdf_files)} PDF files. Starting merge...")
        merger = PdfMerger()
        
        try:
            for filename in pdf_files:
                file_path = os.path.join(input_folder, filename)
                # print(f"Appending: {filename}")
                merger.append(file_path)
            
            output_path = os.path.join(output_folder, f"{os.path.splitext(input_file_name)[0]}_Converted.pdf")
            
            # print("Writing merged file...")
            merger.write(output_path)
            # print(f"Successfully merged {len(pdf_files)} files into: {output_path}")
            
        except Exception as e:
            print(f"An error occurred during merging: {e}")
        finally:
            merger.close()

if __name__ == "__main__":
    merge_pdfs(r"D:\New folder\DocuZone\Ploted", r"D:\New folder\DocuZone\Merged_Output", "Invoice_1.pdf")