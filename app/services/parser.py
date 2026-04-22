import os
from PyPDF2 import PdfReader
import ebooklib
from ebooklib import epub


def parse_txt(content: str) -> list[dict]:
    """Split TXT content into paragraphs by double newlines."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    return [
        {"para_index": i, "page_num": None, "content": para}
        for i, para in enumerate(paragraphs)
    ]


def parse_pdf(file_path: str) -> list[dict]:
    """Extract paragraphs from PDF, tracking page numbers."""
    reader = PdfReader(file_path)
    paragraphs = []
    para_index = 0
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        page_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        for para in page_paragraphs:
            paragraphs.append({
                "para_index": para_index,
                "page_num": page_num,
                "content": para,
            })
            para_index += 1
    return paragraphs


def parse_epub(file_path: str) -> list[dict]:
    """Extract paragraphs from EPUB."""
    book = epub.read_epub(file_path)
    paragraphs = []
    para_index = 0
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        import re
        html_content = item.get_content().decode("utf-8", errors="ignore")
        # Strip HTML tags
        text = re.sub(r"<[^>]+>", "\n", html_content)
        page_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        # Also split by single newlines if double-newline split yields nothing
        if not page_paragraphs:
            page_paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        for para in page_paragraphs:
            if len(para) < 10:
                continue  # Skip very short fragments (likely HTML artifacts)
            paragraphs.append({
                "para_index": para_index,
                "page_num": None,
                "content": para,
            })
            para_index += 1
    return paragraphs


def parse_file(file_path: str, file_type: str) -> list[dict]:
    """Parse a book file into a list of paragraph dicts."""
    if file_type == "txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return parse_txt(content)
    elif file_type == "pdf":
        return parse_pdf(file_path)
    elif file_type == "epub":
        return parse_epub(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")