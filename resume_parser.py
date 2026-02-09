import pdfplumber

def extract_resume_text(pdf_path: str) -> str:
    text = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    # Basic cleanup
    text = text.replace("\t", " ")
    text = " ".join(text.split())

    return text
