"""An announcement from a company outside the scored universe: the card says so, and a temporary score
(computed against the core mills, never saved) can be added without touching any snapshot."""
import csv
import json
from pathlib import Path

from src.adhoc_score import score_one
from src.analyze import ROOT, build_card, demo_cases
from src.quarterly import parse_abstract


def _doc(code: str) -> tuple[dict, dict]:
    case = next(c for c in demo_cases() if c["id"] == "antai_guarantee")
    doc = json.loads((ROOT / case["prediction"]).read_text(encoding="utf-8"))
    doc["security_code"] = code
    return doc, case


def test_card_flags_out_of_scope_issuer():
    doc, case = _doc("600999")                       # not a steel-chain company in the universe
    card = build_card(doc, case["prediction_from"], "2026-09-29", ROOT / "data" / "chain" / "live")
    assert card["in_scope"] is False and card["adhoc"] is False


def test_temporary_score_is_labelled_and_used():
    code = "600104"
    q = ROOT / "data" / "external" / "financials" / "quarterly" / f"{code}_abstract.csv"
    m = ROOT / "data" / "external" / "market" / f"{code}.csv"
    if not (q.exists() and m.exists()):
        return                                        # cached data only exists on the maintainer's machine
    periods = parse_abstract(list(csv.reader(q.open(encoding="utf-8-sig"))))
    prices = [(r["date"], float(r["close"])) for r in csv.DictReader(m.open(encoding="utf-8"))]
    row = score_one(code, "上汽集团", "2026-09-29", periods, prices)
    assert row["peer_group"] == "adhoc" and row["tier"] in ("weak", "medium", "strong")
    doc, case = _doc(code)
    card = build_card(doc, case["prediction_from"], "2026-09-29", ROOT / "data" / "chain" / "live", extra_fragility={code: row})
    assert card["in_scope"] and card["adhoc"]
