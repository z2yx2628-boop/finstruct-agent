import pymupdf
import pytest

from src.document_parser import (
    UnsupportedDocumentTypeError,
    parse_document,
)


def create_pdf(path, text="Test document"):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_routes_pdf_to_pdf_parser(tmp_path):
    pdf_path = tmp_path / "announcement.PDF"
    create_pdf(pdf_path)

    document = parse_document(pdf_path)

    assert document.source_type == "pdf_text"
    assert document.source_name == "announcement.PDF"
    assert document.pages[0].text == "Test document"


def test_missing_document_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_document(tmp_path / "missing.pdf")


def test_unsupported_document_type_is_rejected(tmp_path):
    text_path = tmp_path / "announcement.txt"
    text_path.write_text("test", encoding="utf-8")

    with pytest.raises(UnsupportedDocumentTypeError):
        parse_document(text_path)