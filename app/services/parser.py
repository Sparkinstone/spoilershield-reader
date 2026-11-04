"""Book parsing: TXT / PDF / EPUB → a list of paragraph dicts.

Each paragraph is ``{"para_index": int, "page_num": int | None, "content": str}``
with ``para_index`` sequential across the whole book.
"""

from __future__ import annotations

import html
import re

import ebooklib
from ebooklib import epub
from PyPDF2 import PdfReader

# GB18030 is attempted before Big5: it is a superset of GBK/GB2312, which covers
# the overwhelming majority of Chinese ebooks. latin-1 always succeeds and is the
# last resort so a book with an unknown encoding still opens.
_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1")

_SCRIPT_STYLE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_BLOCK_TAG = re.compile(
    r"</?(?:p|div|br|h[1-6]|li|tr|section|article|blockquote|pre)[^>]*>", re.IGNORECASE
)
_ANY_TAG = re.compile(r"<[^>]+>")
_SENTENCE_BREAK = re.compile(r"(?<=[。！？!?；;])")


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _decode_bytes(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def read_text_file(file_path: str) -> str:
    with open(file_path, "rb") as handle:
        return _decode_bytes(handle.read())


def split_paragraphs(text: str, *, min_length: int = 1, split_single_newlines: bool = False) -> list[str]:
    """Split plain text on blank lines; optionally treat every line as a paragraph."""
    text = _normalize(text)
    blocks = [block.strip() for block in re.split(r"\n\s*\n+", text) if block.strip()]

    if split_single_newlines and len(blocks) <= 1:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if len(lines) > 1:
            blocks = lines

    paragraphs: list[str] = []
    for block in blocks:
        cleaned = re.sub(r"[ \t\u3000]+", " ", block).strip()
        if cleaned and len(cleaned) >= min_length:
            paragraphs.append(cleaned)
    return paragraphs


def _split_long_text(text: str, limit: int = 1000) -> list[str]:
    """Split an over-long block at sentence boundaries so one page is not one paragraph."""
    if len(text) <= limit:
        return [text]
    pieces, current = [], ""
    for sentence in _SENTENCE_BREAK.split(text):
        if not sentence:
            continue
        if current and len(current) + len(sentence) > limit:
            pieces.append(current.strip())
            current = sentence
        else:
            current += sentence
    if current.strip():
        pieces.append(current.strip())
    return [piece for piece in pieces if piece]


def _pdf_page_paragraphs(page_text: str) -> list[str]:
    page_text = _normalize(page_text)
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n+", page_text):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        # Drop running headers/footers that are just a page number.
        lines = [line for line in lines if not (len(line) <= 4 and line.isdigit())]
        if not lines:
            continue

        joined = lines[0]
        for line in lines[1:]:
            # Latin text wraps with a space; CJK wraps without one.
            if re.search(r"[A-Za-z0-9,;:]$", joined) and re.match(r"[A-Za-z0-9]", line):
                joined += " " + line
            else:
                joined += line
        paragraphs.extend(_split_long_text(joined))
    return paragraphs


def parse_txt(content: str) -> list[dict]:
    """Split TXT content into paragraphs — blank-line first, single newline fallback."""
    paragraphs = split_paragraphs(content, split_single_newlines=True)
    return [
        {"para_index": index, "page_num": None, "content": paragraph}
        for index, paragraph in enumerate(paragraphs)
    ]


def parse_pdf(file_path: str) -> list[dict]:
    """Extract paragraphs from PDF, tracking page numbers."""
    reader = PdfReader(file_path)
    if getattr(reader, "is_encrypted", False):
        raise ValueError("PDF 已加密，无法解析")

    paragraphs: list[dict] = []
    para_index = 0
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for content in _pdf_page_paragraphs(text):
            paragraphs.append(
                {"para_index": para_index, "page_num": page_num, "content": content}
            )
            para_index += 1

    if not paragraphs:
        raise ValueError("PDF 中未提取到文本（可能是扫描版）")
    return paragraphs


def _html_to_text(raw_html: str) -> str:
    text = _SCRIPT_STYLE.sub(" ", raw_html)
    text = _BLOCK_TAG.sub("\n\n", text)
    text = _ANY_TAG.sub("", text)
    text = html.unescape(text)
    text = _normalize(text)
    return re.sub(r"[ \t\u3000]+", " ", text)


def _epub_documents(book) -> list[tuple[str, list[str]]]:
    documents = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        name = item.get_name()
        try:
            if hasattr(item, "is_chapter") and not item.is_chapter():
                continue
        except Exception:  # pragma: no cover - defensive, ebooklib internals vary
            pass
        raw_html = _decode_bytes(item.get_content())
        paragraphs = split_paragraphs(_html_to_text(raw_html), min_length=10)
        documents.append((name, paragraphs))
    return documents


def parse_epub(file_path: str) -> list[dict]:
    """Extract paragraphs from EPUB."""
    try:
        book = epub.read_epub(file_path)
    except Exception as exc:  # ebooklib raises a variety of errors
        raise ValueError(f"EPUB 解析失败：{exc}") from exc

    paragraphs: list[dict] = []
    para_index = 0
    for _, document_paragraphs in _epub_documents(book):
        for content in document_paragraphs:
            paragraphs.append(
                {"para_index": para_index, "page_num": None, "content": content}
            )
            para_index += 1

    if not paragraphs:
        raise ValueError("EPUB 中未提取到正文")
    return paragraphs


def parse_epub_toc(file_path: str) -> list[dict]:
    """Extract the table of contents with best-effort paragraph anchors.

    Uses the same document/paragraph splitting as :func:`parse_epub`, so the
    anchors match the paragraphs actually rendered in the reader.
    """
    try:
        book = epub.read_epub(file_path)
    except Exception:
        return []

    doc_para_start: dict[str, int] = {}
    para_index = 0
    for name, document_paragraphs in _epub_documents(book):
        doc_para_start[name] = para_index
        para_index += len(document_paragraphs)

    def _resolve(href: str) -> int | None:
        href = (href or "").split("#")[0]
        if not href:
            return None
        start = doc_para_start.get(href) or doc_para_start.get(href.lstrip("/"))
        if start is not None:
            return start
        base = href.split("/")[-1]
        for name, value in doc_para_start.items():
            if name.endswith(base):
                return value
        return None

    toc_items: list[dict] = []

    def _flatten(nodes, depth: int = 0) -> None:
        for node in nodes:
            if isinstance(node, tuple):
                section, children = node
                toc_items.append(
                    {
                        "title": (section.title or "（无标题）").strip(),
                        "para_index": _resolve(section.href) or 0,
                        "depth": depth,
                    }
                )
                _flatten(children, depth + 1)
            elif hasattr(node, "href"):
                toc_items.append(
                    {
                        "title": (getattr(node, "title", None) or "（无标题）").strip(),
                        "para_index": _resolve(node.href) or 0,
                        "depth": depth,
                    }
                )

    try:
        _flatten(book.toc)
    except Exception:  # pragma: no cover - malformed NCX should not break reading
        return []
    return toc_items


def parse_file(file_path: str, file_type: str) -> list[dict]:
    """Parse a book file into a list of paragraph dicts."""
    file_type = (file_type or "").lower().lstrip(".")
    try:
        if file_type == "txt":
            paragraphs = parse_txt(read_text_file(file_path))
        elif file_type == "pdf":
            paragraphs = parse_pdf(file_path)
        elif file_type == "epub":
            paragraphs = parse_epub(file_path)
        else:
            raise ValueError(f"不支持的文件类型：{file_type}")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"文件解析失败：{exc}") from exc

    if not paragraphs:
        raise ValueError("文件中没有可阅读的段落")
    return paragraphs
