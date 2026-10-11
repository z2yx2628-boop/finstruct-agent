import importlib.util
from pathlib import Path

from src.validity import related_window

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scan", ROOT / "scripts" / "scan_agreement_periods.py")
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def test_agreement_extends_estimate_year():
    assert related_window(2025, "2024-10-30", "2027-12-31") == ("2024-10-30", "2027-12-31")


def test_agreement_never_shortens():
    assert related_window(2025, "2024-10-30", "2024-12-31") == ("2024-10-30", "2025-12-31")
    assert related_window(2025, "2024-10-30", "") == ("2024-10-30", "2025-12-31")


def test_explicit_period_sentence():
    pages = [{"page": 3, "text": "协议有效期自2025 年1 月1 日起至2027 年12 月31 日止，为期三年。"}]
    assert scan.find_period(pages)[:3] == ("2025-01-01", "2027-12-31", 3)


def test_year_span_next_to_agreement():
    pages = [{"page": 1, "text": "关于2024 至2026 年度持续关联交易的公告"}]
    assert scan.find_period(pages)[:2] == ("2024-01-01", "2026-12-31")


def test_spans_longer_than_three_years_ignored():
    pages = [{"page": 1, "text": "2019-2026 年度关联交易协议"}]
    assert scan.find_period(pages) is None
