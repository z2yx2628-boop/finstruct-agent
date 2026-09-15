import hashlib
import json
from pathlib import Path

import pymupdf

from schemas.common import ParsedDocument, ParsedPage


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = PROJECT_ROOT / "data" / "raw" / "sample_pledge.pdf"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "sample_pledge_pages.json"


def calculate_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def parse_pdf(pdf_path: Path) -> ParsedDocument:
    """Parse a PDF into the common document structure."""
    pdf_path = Path(pdf_path).resolve()
    pages: list[ParsedPage] = []

    with pymupdf.open(pdf_path) as document:
        metadata = {
            key: value
            for key, value in document.metadata.items()
            if value
        }

        for page_number, page in enumerate(document, start=1):
            pages.append(
                ParsedPage(
                    page=page_number,
                    text=page.get_text("text").strip(),
                )
            )

    text_char_count = sum(len(page.text) for page in pages)
    empty_page_count = sum(not page.text for page in pages)
    needs_ocr = text_char_count == 0

    metadata.update(
        {
            "page_count": len(pages),
            "text_char_count": text_char_count,
            "empty_page_count": empty_page_count,
            "needs_ocr": needs_ocr,
        }
    )

    return ParsedDocument(
        document_id=pdf_path.stem,
        source_type="pdf_scan" if needs_ocr else "pdf_text",
        source_name=pdf_path.name,
        source_path=str(pdf_path),
        sha256=calculate_sha256(pdf_path),
        pages=pages,
        metadata=metadata,
    )


def extract_pages(pdf_path: Path) -> list[dict]:
    """Compatibility interface used by the existing pledge pipeline."""
    document = parse_pdf(pdf_path)

    return [
        {
            "page": page.page,
            "text": page.text,
        }
        for page in document.pages
    ]


if __name__ == "__main__":
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF not found: {PDF_PATH}")

    parsed_document = parse_pdf(PDF_PATH)
    extracted_pages = extract_pages(PDF_PATH)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(extracted_pages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Saved extracted text to: {OUTPUT_PATH}")
    print(f"Source type: {parsed_document.source_type}")
    print(f"SHA256: {parsed_document.sha256}")
    print(f"Successfully read {len(extracted_pages)} pages.")