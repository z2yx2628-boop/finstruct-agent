"""Optical character recognition for scanned pages and images.

The default engine is RapidOCR (local, CPU, no API cost), installed with
`pip install rapidocr_onnxruntime`. When it is not installed, OCR is
reported as unavailable and pages keep their native text only, so text
PDFs behave exactly as before.
"""
from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Protocol

LOW_CONFIDENCE_THRESHOLD = 0.90
OCR_DPI = 200


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float | None
    line_count: int


class OcrEngine(Protocol):
    name: str

    def recognize(self, image_bytes: bytes) -> OcrResult:
        ...


def _group_lines(boxes: list[tuple[float, float, float, str, float]]) -> list[str]:
    """Sort OCR boxes into reading order: top-to-bottom, then left-to-right."""
    lines: list[list[tuple[float, float, float, str, float]]] = []
    for box in sorted(boxes):
        top, _, height, _, _ = box
        for line in lines:
            line_top, _, line_height, _, _ = line[0]
            if abs(top - line_top) <= max(height, line_height) * 0.5:
                line.append(box)
                break
        else:
            lines.append([box])
    return [
        " ".join(item[3] for item in sorted(line, key=lambda item: item[1]))
        for line in lines
    ]


_DIGIT_SEPARATOR = re.compile(r"(?<=\d)\s*([，,．.：:])\s*(?=\d)")
_SEPARATOR_MAP = {"，": ",", ",": ",", "．": ".", ".": ".", "：": ".", ":": "."}


def clean_ocr_numbers(text: str) -> str:
    """Repair number punctuation that OCR commonly gets wrong.

    Only characters between two digits are touched, e.g. "10，808" becomes
    "10,808" and "3．5" becomes "3.5". Text outside numbers is unchanged.
    """
    def replace(match: re.Match) -> str:
        return _SEPARATOR_MAP[match.group(1)]

    text = _DIGIT_SEPARATOR.sub(replace, text)
    # "10,808:万元" -> "10,808万元": a stray colon or dot before a unit.
    return re.sub(r"(?<=\d)[：:．.](?=[万亿千百]?[元吨股])", "", text)


class RapidOcrEngine:
    name = "RapidOCR (onnxruntime)"

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def recognize(self, image_bytes: bytes) -> OcrResult:
        result, _ = self._engine(image_bytes)
        if not result:
            return OcrResult(text="", confidence=None, line_count=0)
        boxes = []
        scores = []
        for points, text, score in result:
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            boxes.append((min(ys), min(xs), max(ys) - min(ys), text, float(score)))
            scores.append(float(score))
        lines = _group_lines(boxes)
        return OcrResult(
            text=clean_ocr_numbers("\n".join(lines)),
            confidence=round(sum(scores) / len(scores), 4),
            line_count=len(lines),
        )


@lru_cache(maxsize=1)
def get_default_engine() -> OcrEngine | None:
    try:
        return RapidOcrEngine()
    except Exception:
        return None
