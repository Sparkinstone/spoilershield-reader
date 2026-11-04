"""Parser tests: encodings, paragraph splitting, EPUB/TOC, bad inputs."""

from __future__ import annotations

from pathlib import Path

import pytest
from ebooklib import epub

from app.services.parser import (
    _pdf_page_paragraphs,
    parse_epub,
    parse_epub_toc,
    parse_file,
    parse_txt,
    read_text_file,
    split_paragraphs,
)


# ------------------------------------------------------------------------ TXT
def test_parse_txt_splits_on_blank_lines():
    result = parse_txt("Paragraph one.\n\nParagraph two.\n\nParagraph three.")
    assert len(result) == 3
    assert [item["para_index"] for item in result] == [0, 1, 2]
    assert result[0]["content"] == "Paragraph one."


def test_parse_txt_tolerates_many_blank_lines():
    result = parse_txt("Para 1.\n\n\n\nPara 2.\n\n\nPara 3.")
    assert [item["content"] for item in result] == ["Para 1.", "Para 2.", "Para 3."]


def test_parse_txt_falls_back_to_single_newlines():
    # Chinese .txt files frequently use one newline per paragraph and no blank line.
    result = parse_txt("第一段内容。\n第二段内容。\n第三段内容。")
    assert [item["content"] for item in result] == ["第一段内容。", "第二段内容。", "第三段内容。"]


def test_parse_txt_keeps_single_paragraph():
    result = parse_txt("Just one paragraph with no breaks.")
    assert len(result) == 1


def test_split_paragraphs_min_length():
    assert split_paragraphs("a\n\nlong enough", min_length=5) == ["long enough"]


def test_read_text_file_handles_gbk(tmp_path):
    path = tmp_path / "gbk.txt"
    path.write_bytes("中文编码测试。".encode("gbk"))

    assert read_text_file(str(path)) == "中文编码测试。"


def test_read_text_file_handles_utf8_bom(tmp_path):
    path = tmp_path / "bom.txt"
    path.write_bytes("\ufeff开头有 BOM。".encode("utf-8"))

    assert read_text_file(str(path)) == "开头有 BOM。"


def test_parse_file_txt_end_to_end(tmp_path):
    path = tmp_path / "test.txt"
    path.write_text("Para one.\n\nPara two.", encoding="utf-8")

    result = parse_file(str(path), "txt")

    assert [item["content"] for item in result] == ["Para one.", "Para two."]


# ------------------------------------------------------------------------ PDF
def test_pdf_page_paragraphs_joins_wrapped_lines():
    page = "这是第一行，\n接着第二行。\n\n这是另一段。"
    paragraphs = _pdf_page_paragraphs(page)

    assert paragraphs == ["这是第一行，接着第二行。", "这是另一段。"]


def test_pdf_page_paragraphs_drops_page_numbers():
    assert _pdf_page_paragraphs("12\n\n正文内容。") == ["正文内容。"]


def test_parse_file_rejects_corrupt_pdf(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"definitely not a pdf")

    with pytest.raises(ValueError):
        parse_file(str(path), "pdf")


# ----------------------------------------------------------------------- EPUB
def _make_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("test-id")
    book.set_title("测试书")
    book.set_language("zh")
    chapter = epub.EpubHtml(title="第一章", file_name="chap_01.xhtml", lang="zh")
    chapter.content = (
        "<h1>第一章</h1>"
        "<p>这是第一段足够长的正文内容。</p>"
        "<p>这是第二段足够长的正文内容。</p>"
    )
    book.add_item(chapter)
    book.toc = (chapter,)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]
    epub.write_epub(str(path), book)


def test_parse_epub_extracts_paragraphs(tmp_path):
    path = tmp_path / "book.epub"
    _make_epub(path)

    paragraphs = parse_epub(str(path))

    contents = [item["content"] for item in paragraphs]
    assert any("第一段" in content for content in contents)
    assert any("第二段" in content for content in contents)
    assert [item["para_index"] for item in paragraphs] == list(range(len(paragraphs)))


def test_parse_epub_toc_anchor_matches_paragraphs(tmp_path):
    path = tmp_path / "book.epub"
    _make_epub(path)

    toc = parse_epub_toc(str(path))

    assert toc
    assert toc[0]["para_index"] == 0


def test_parse_file_rejects_corrupt_epub(tmp_path):
    path = tmp_path / "broken.epub"
    path.write_bytes(b"not an epub")

    with pytest.raises(ValueError):
        parse_file(str(path), "epub")


# ------------------------------------------------------------------- generic
def test_parse_file_rejects_unknown_type(tmp_path):
    path = tmp_path / "book.doc"
    path.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="不支持"):
        parse_file(str(path), "doc")


def test_parse_file_rejects_empty_text(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("   \n\n  ", encoding="utf-8")

    with pytest.raises(ValueError):
        parse_file(str(path), "txt")
