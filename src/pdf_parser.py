import hashlib
import json
from pathlib import Path

import pymupdf

from schemas.common import ParsedDocument, ParsedPage
from src.ocr import OCR_DPI, OcrEngine, get_default_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = PROJECT_ROOT / "data" / "raw" / "sample_pledge.pdf"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "sample_pledge_pages.json"

# Below this many native characters, a page that also has images is a scan.
MIN_NATIVE_CHARS = 20

_DEFAULT = object()


def calculate_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def page_tables(page) -> list[dict]:
    """Detected tables as cell rows, so table numbers are not glued together."""
    try:
        finder = page.find_tables()
    except Exception:
        return []
    tables = []
    for index, table in enumerate(finder.tables, start=1):
        try:
            rows = table.extract()
        except Exception:
            continue
        cleaned = [
            [("" if cell is None else " ".join(str(cell).split())) for cell in row]
            for row in rows
        ]
        if cleaned:
            tables.append({"index": index, "rows": cleaned})
    return tables


def is_scanned_page(page, native_text: str) -> bool:
    """A page needs OCR when it has no text, or only a few characters of
    text on top of embedded images (e.g. a scanned page with a stamp)."""
    if not native_text:
        return True
    if len(native_text) >= MIN_NATIVE_CHARS:
        return False
    try:
        return bool(page.get_images())
    except Exception:
        return False


def parse_pdf(pdf_path: Path, ocr_engine=_DEFAULT) -> ParsedDocument:
    """Parse a PDF page by page, OCR-ing pages that have no native text."""
    pdf_path = Path(pdf_path).resolve()
    engine = get_default_engine() if ocr_engine is _DEFAULT else ocr_engine
    pages: list[ParsedPage] = []
    ocr_pages: list[int] = []
    scanned_pages: list[int] = []

    with pymupdf.open(pdf_path) as document:
        metadata = {
            key: value
            for key, value in document.metadata.items()
            if value
        }

        for page_number, page in enumerate(document, start=1):
            native_text = page.get_text("text").strip()
            parsed = ParsedPage(
                page=page_number,
                text=native_text,
                tables=page_tables(page) if native_text else [],
            )
            if is_scanned_page(page, native_text):
                scanned_pages.append(page_number)
                if engine is not None:
                    image = page.get_pixmap(dpi=OCR_DPI).tobytes("png")
                    result = engine.recognize(image)
                    if len(result.text.strip()) > len(native_text):
                        parsed = ParsedPage(
                            page=page_number,
                            text=result.text.strip(),
                            ocr_used=True,
                            ocr_confidence=result.confidence,
                        )
                        ocr_pages.append(page_number)
            pages.append(parsed)

    text_char_count = sum(len(page.text) for page in pages)
    empty_page_count = sum(not page.text for page in pages)
    if scanned_pages and len(scanned_pages) == len(pages):
        source_type = "pdf_scan"
    elif scanned_pages:
        source_type = "pdf_mixed"
    else:
        source_type = "pdf_text"

    metadata.update(
        {
            "page_count": len(pages),
            "text_char_count": text_char_count,
            "empty_page_count": empty_page_count,
            "needs_ocr": bool(scanned_pages),
            "scanned_pages": scanned_pages,
            "ocr_pages": ocr_pages,
            "ocr_engine": getattr(engine, "name", None) if ocr_pages else None,
            "ocr_available": engine is not None,
        }
    )

    return ParsedDocument(
        document_id=pdf_path.stem,
        source_type=source_type,
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
