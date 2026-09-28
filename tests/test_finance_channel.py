"""集团财务公司存款通道: point-in-time by publication date, every row sourced, display only."""
import csv
from pathlib import Path

from src.finance_channel import DEPOSITS, by_finance_company, deposit

ROOT = Path(__file__).resolve().parents[1]


def test_every_row_has_a_source_and_a_number():
    with DEPOSITS.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows and all(r["source_url"].startswith("http") and r["evidence_text"] and float(r["deposit_yi"]) >= 0
                        for r in rows)


def test_deposit_is_used_only_after_publication():
    assert deposit("600010", "2026-04-17") is None
    assert deposit("600010", "2026-04-18")["deposit_yi"] == 41.67


def test_group_view_sums_members():
    day = "2026-09-27"
    with (ROOT / "data" / "snapshots" / day / "fragility.csv").open(encoding="utf-8-sig", newline="") as f:
        fr = {r["security_code"]: r for r in csv.DictReader(f)}
    groups = by_finance_company(day, fr, {})
    for g in groups:
        assert abs(g["total_yi"] - sum(m["deposit_yi"] for m in g["members"])) < 0.01
