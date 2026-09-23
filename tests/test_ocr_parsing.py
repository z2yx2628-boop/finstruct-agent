import pymupdf

from src.image_parser import parse_image
from src.ocr import OcrResult, _group_lines
from src.pdf_parser import parse_pdf


class FakeEngine:
    name = "fake-ocr"

    def __init__(self, text="扫描页识别文字 投资总额10,808万元", confidence=0.97):
        self.text = text
        self.confidence = confidence
        self.calls = 0

    def recognize(self, image_bytes: bytes) -> OcrResult:
        assert image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
        self.calls += 1
        return OcrResult(self.text, self.confidence, 1)


def make_pdf(path, texts):
    document = pymupdf.open()
    for text in texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def test_text_pdf_does_not_call_ocr(tmp_path):
    path = tmp_path / "text.pdf"
    make_pdf(path, ["Financial announcement with enough native text"])
    engine = FakeEngine()

    document = parse_pdf(path, ocr_engine=engine)

    assert engine.calls == 0
    assert document.source_type == "pdf_text"
    assert document.pages[0].ocr_used is False
    assert document.metadata["ocr_pages"] == []


def test_mixed_pdf_ocrs_only_the_empty_page(tmp_path):
    path = tmp_path / "mixed.pdf"
    make_pdf(path, ["Financial announcement with enough native text", None])
    engine = FakeEngine()

    document = parse_pdf(path, ocr_engine=engine)

    assert engine.calls == 1
    assert document.source_type == "pdf_mixed"
    assert document.pages[0].ocr_used is False
    assert document.pages[1].ocr_used is True
    assert document.pages[1].ocr_confidence == 0.97
    assert "10,808" in document.pages[1].text
    assert document.metadata["ocr_pages"] == [2]


def test_scanned_pdf_without_ocr_engine_keeps_empty_text(tmp_path):
    path = tmp_path / "scan.pdf"
    make_pdf(path, [None])

    document = parse_pdf(path, ocr_engine=None)

    assert document.source_type == "pdf_scan"
    assert document.metadata["needs_ocr"] is True
    assert document.metadata["text_char_count"] == 0
    assert document.metadata["ocr_available"] is False


def test_image_is_parsed_with_ocr(tmp_path):
    path = tmp_path / "notice.png"
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), 0)
    pixmap.save(str(path))
    engine = FakeEngine(confidence=0.8)

    document = parse_image(path, ocr_engine=engine)

    assert document.source_type == "image"
    assert document.pages[0].ocr_used is True
    assert document.pages[0].ocr_confidence == 0.8


def test_ocr_boxes_are_read_in_line_order():
    boxes = [
        (50.0, 10.0, 20.0, "第二行", 0.9),
        (10.0, 200.0, 20.0, "右", 0.9),
        (12.0, 10.0, 20.0, "左", 0.9),
    ]

    assert _group_lines(boxes) == ["左 右", "第二行"]


def test_text_pdf_records_table_cells(tmp_path):
    path = tmp_path / "table.pdf"
    document = pymupdf.open()
    page = document.new_page()
    for row, values in enumerate((("Project", "Amount"), ("A", "8,000.00"), ("B", "6,000.00"))):
        for column, value in enumerate(values):
            x0, y0 = 72 + column * 150, 72 + row * 30
            page.draw_rect(pymupdf.Rect(x0, y0, x0 + 150, y0 + 30))
            page.insert_text((x0 + 5, y0 + 20), value)
    document.save(path)
    document.close()

    parsed = parse_pdf(path, ocr_engine=None)

    cells = [cell for table in parsed.pages[0].tables for row in table["rows"] for cell in row]
    assert "8,000.00" in cells
    assert "6,000.00" in cells
