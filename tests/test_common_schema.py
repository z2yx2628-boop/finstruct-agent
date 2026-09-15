import pytest
from pydantic import ValidationError

from schemas.common import ParsedDocument, ParsedPage


def test_valid_parsed_document():
    document = ParsedDocument(
        document_id="sample",
        source_type="pdf_text",
        source_name="sample.pdf",
        source_path="data/raw/sample.pdf",
        sha256="a" * 64,
        pages=[ParsedPage(page=1, text="测试文本")],
    )

    assert document.pages[0].page == 1
    assert document.pages[0].ocr_used is False


def test_source_location_is_required():
    with pytest.raises(ValidationError):
        ParsedDocument(
            document_id="sample",
            source_type="pdf_text",
            source_name="sample.pdf",
            sha256="a" * 64,
        )


def test_invalid_sha256_is_rejected():
    with pytest.raises(ValidationError):
        ParsedDocument(
            document_id="sample",
            source_type="pdf_text",
            source_name="sample.pdf",
            source_path="sample.pdf",
            sha256="invalid",
        )