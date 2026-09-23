from pathlib import Path

from schemas.common import ParsedDocument, ParsedPage
from src.ocr import get_default_engine
from src.pdf_parser import calculate_sha256

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")

_DEFAULT = object()


def parse_image(image_path: Path, ocr_engine=_DEFAULT) -> ParsedDocument:
    """OCR a single announcement image (screenshot, photo or scan)."""
    image_path = Path(image_path).resolve()
    engine = get_default_engine() if ocr_engine is _DEFAULT else ocr_engine
    if engine is None:
        raise RuntimeError(
            "Image input requires OCR. Install it with: "
            "pip install rapidocr_onnxruntime"
        )
    result = engine.recognize(image_path.read_bytes())
    text = result.text.strip()
    return ParsedDocument(
        document_id=image_path.stem,
        source_type="image",
        source_name=image_path.name,
        source_path=str(image_path),
        sha256=calculate_sha256(image_path),
        pages=[ParsedPage(
            page=1,
            text=text,
            ocr_used=True,
            ocr_confidence=result.confidence,
        )],
        metadata={
            "page_count": 1,
            "text_char_count": len(text),
            "empty_page_count": 0 if text else 1,
            "needs_ocr": True,
            "scanned_pages": [1],
            "ocr_pages": [1] if text else [],
            "ocr_engine": engine.name,
            "ocr_available": True,
        },
    )
