"""The Baosteel appendix rows (read by rules) must add up to the announcement's own category totals."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "outputs" / "manual_freeze" / "related_party" / "related_dev_001_600019_annual_estimate.json"
# 2026 body table, page 3 of 临2026-013 (百万元)
TOTALS = {"purchase_goods": 84630.77, "sell_goods": 30115.74, "receive_services": 12587.21,
          "provide_services": 4970.09, "lease_in": 628.96, "lease_out": 242.09}


def test_appendix_rows_match_body_totals():
    doc = json.loads(DOC.read_text(encoding="utf-8"))
    assert doc["security_code"] == "600019" and doc["estimate_year"] == 2026
    sums = {}
    for t in doc["transactions"]:
        assert t["counterparty"] and t["estimated_amount"] > 0 and 23 <= t["source_page"] <= 30
        sums[t["transaction_category"]] = sums.get(t["transaction_category"], 0) + t["estimated_amount"]
    for cat, total in TOTALS.items():
        assert abs(sums[cat] - total) < 0.1, cat


def test_parent_and_largest_counterparties_are_named():
    rows = json.loads(DOC.read_text(encoding="utf-8"))["transactions"]
    parent = [t for t in rows if t["relationship"] == "parent_or_controlling_shareholder"]
    assert parent and all(t["counterparty"] == "中国宝武钢铁集团有限公司" for t in parent)
    top = max((t for t in rows if t["transaction_category"] == "purchase_goods"), key=lambda t: t["estimated_amount"])
    assert top["counterparty"] == "马钢（集团）控股有限公司"
