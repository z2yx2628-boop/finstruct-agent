"""Policy-shock library: point-in-time inputs, documented constants, missing data stays missing."""
import csv
from pathlib import Path

from src.policy_shock import CBAM_FACTOR, carbon, carbon_cost_per_ton, export_change, overseas_share, usable_from

ROOT = Path(__file__).resolve().parents[1]


def fragility(day="2026-09-27"):
    with (ROOT / "data" / "snapshots" / day / "fragility.csv").open(encoding="utf-8-sig", newline="") as f:
        return {r["security_code"]: r for r in csv.DictReader(f)}


def test_annual_report_is_used_only_after_april_30():
    assert usable_from("2025-12-31") == "2026-04-30"
    assert overseas_share("600019", "2026-04-29")["period"] == "2024-12-31"
    assert overseas_share("600019", "2026-04-30")["period"] == "2025-12-31"


def test_cbam_schedule_and_cost_formula():
    assert CBAM_FACTOR[2026] == 0.025 and CBAM_FACTOR[2030] == 0.485 and CBAM_FACTOR[2034] == 1.0
    cost = carbon_cost_per_ton("BF-BOF", eu_price=600, year=2030, domestic_price=60)
    assert abs(cost["cbam"] - 2.34 * 0.485 * 540) < 0.1


def test_missing_overseas_split_is_not_filled():
    rows = export_change(fragility(), "2026-09-27", 0.05)
    assert any(r["overseas_share"] is None and r["index"] is None for r in rows)
    assert all(r["index"] is None or r["index"] > 0 for r in rows)


def test_carbon_ranking_is_deterministic():
    a = carbon(fragility(), "2026-09-27", 600, 2027, 60)
    b = carbon(fragility(), "2026-09-27", 600, 2027, 60)
    assert [r["code"] for r in a] == [r["code"] for r in b] and len(a) == 24


def test_trade_extraction_reads_iron_ore_rows_with_empty_cells():
    from scripts.extract_annual_trade import numbers
    assert numbers("自供                           /          /                    /          /") == [None, None, None, None]
    assert numbers("国外进口                    9,091,366   8,953,785            7,051,611   8,087,631")[:3] == [9091366.0, 8953785.0, 7051611.0]
    assert numbers("自供                              -           -                    -           -") == [None, None, None, None]
