import pdfplumber

def detect_pdf_type(pdf_path: str) -> str:
    try:
        text_parts = []

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text(layout=True)
                if text:
                    text_parts.append(text)

        extracted_text = "".join(text_parts)
        clean_text = "".join(extracted_text.split())

        if len(clean_text) >= 200:
            return "digital"
        else:
            return "scanned"

    except Exception as e:
        print(f"Error: {e}")
        return "scanned"

if __name__ == "__main__":
    pdf_path = r"D:\DocuZone\AgenticDocuZone\input\1202503281136421852 (2).pdf"
    pdf_type = detect_pdf_type(pdf_path)
    # print(f"Detected PDF type: {pdf_type}")