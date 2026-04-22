# tests/test_parser.py
import pytest
from app.services.parser import parse_file, parse_txt, parse_pdf, parse_epub


def test_parse_txt():
    content = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    result = parse_txt(content)
    assert len(result) == 3
    assert result[0]["content"] == "Paragraph one."
    assert result[0]["para_index"] == 0
    assert result[1]["para_index"] == 1


def test_parse_txt_empty_lines():
    content = "Para 1.\n\n\n\nPara 2.\n\n\nPara 3."
    result = parse_txt(content)
    assert len(result) == 3


def test_parse_txt_single_paragraph():
    content = "Just one paragraph with no breaks."
    result = parse_txt(content)
    assert len(result) == 1
    assert result[0]["content"] == "Just one paragraph with no breaks."


def test_parse_file_txt(tmp_path):
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("Para one.\n\nPara two.")
    result = parse_file(str(txt_file), "txt")
    assert len(result) == 2