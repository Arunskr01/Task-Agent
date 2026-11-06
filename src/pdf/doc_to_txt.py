import pypandoc  # pip install pypandoc


def doc_to_txt(input_file, output_file):
    pypandoc.convert_file(input_file, "plain", outputfile=output_file, extra_args=["--wrap=none"])


def doc_to_text(input_file: str) -> str:
    """
    Converts a Word document (.doc, .docx) directly into a plain text string.
    """
    return pypandoc.convert_file(input_file, "plain", extra_args=["--wrap=none"])
