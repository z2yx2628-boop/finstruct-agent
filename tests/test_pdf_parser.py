import pymupdf

from src.pdf_parser import extract_pages, parse_pdf


def create_pdf(path, text: str | None = None):
    document = pymupdf.open()
    page = document.new_page()

    if text:
        page.insert_text((72, 72), text)

    document.save(path)
    document.close()


def test_parse_text_pdf(tmp_path):
    pdf_path = tmp_path / "text.pdf"
    create_pdf(pdf_path, "Financial announcement")

    document = parse_pdf(pdf_path)

    assert document.source_type == "pdf_text"
    assert document.source_name == "text.pdf"
    assert document.pages[0].text == "Financial announcement"
    assert len(document.sha256) == 64
    assert document.metadata["needs_ocr"] is False


def test_detect_scanned_or_empty_pdf(tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    create_pdf(pdf_path)

    document = parse_pdf(pdf_path)

    assert document.source_type == "pdf_scan"
    assert document.metadata["needs_ocr"] is True


def test_legacy_extract_pages_interface(tmp_path):
    pdf_path = tmp_path / "legacy.pdf"
    create_pdf(pdf_path, "Legacy interface")

    pages = extract_pages(pdf_path)

    assert pages == [{"page": 1, "text": "Legacy interface"}]