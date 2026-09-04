import json
from pathlib import Path

import pymupdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = PROJECT_ROOT / "data" / "raw" / "sample_pledge.pdf"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "sample_pledge_pages.json"

def extract_pages(pdf_path: Path) -> list[dict]:
    """Extract text from a PDF while preserving page numbers."""
    pages = []

    with pymupdf.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            pages.append(
                {
                    "page": page_number,
                    "text": page.get_text("text").strip(),
                }
            )

    return pages


if __name__ == "__main__":
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF not found: {PDF_PATH}")

    extracted_pages = extract_pages(PDF_PATH)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(extracted_pages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Saved extracted text to: {OUTPUT_PATH}")
    print(f"Successfully read {len(extracted_pages)} pages.")

    for item in extracted_pages:
        preview = item["text"][:150].replace("\n", " ")
        print(f"Page {item['page']}: {preview}")