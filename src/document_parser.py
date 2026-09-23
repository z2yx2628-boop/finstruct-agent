from pathlib import Path
from typing import Callable

from schemas.common import ParsedDocument
from src.image_parser import IMAGE_SUFFIXES, parse_image
from src.office_parser import (
    SPREADSHEET_SUFFIXES,
    WORD_SUFFIXES,
    parse_docx,
    parse_spreadsheet,
)
from src.pdf_parser import parse_pdf
from src.web_parser import HTML_SUFFIXES, parse_html


class UnsupportedDocumentTypeError(ValueError):
    pass


Parser = Callable[[Path], ParsedDocument]

PARSERS: dict[str, Parser] = {
    ".pdf": parse_pdf,
    **{suffix: parse_image for suffix in IMAGE_SUFFIXES},
    **{suffix: parse_html for suffix in HTML_SUFFIXES},
    **{suffix: parse_docx for suffix in WORD_SUFFIXES},
    **{suffix: parse_spreadsheet for suffix in SPREADSHEET_SUFFIXES},
}


def parse_document(source_path: str | Path) -> ParsedDocument:
    """Route a local document to the correct parser."""
    path = Path(source_path).expanduser().resolve()

    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    if not path.is_file():
        raise ValueError(f"Document path is not a file: {path}")

    parser = PARSERS.get(path.suffix.lower())

    if parser is None:
        supported = ", ".join(sorted(PARSERS))
        raise UnsupportedDocumentTypeError(
            f"Unsupported document type: {path.suffix or '<none>'}. "
            f"Supported types: {supported}"
        )

    return parser(path)