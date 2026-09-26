from src.chain_inputs import edges_from, signals_from
from src.validity import add_months, is_active, related_window


def test_add_months_handles_month_ends():
    assert add_months("2024-01-31", 1) == "2024-02-29" and add_months("2024-04-26", 12) == "2025-04-26"


def test_related_estimate_is_in_force_only_for_its_year():
    frm, to = related_window(2025, "2024-12-11")
    assert (frm, to) == ("2024-12-11", "2025-12-31")
    row = {"valid_from": frm, "valid_to": to}
    assert is_active(row, "2025-06-30") and not is_active(row, "2026-03-01") and not is_active(row, "2024-12-01")


def test_guarantee_uses_stated_end_date_else_default_and_released_makes_no_edge():
    doc = {"security_code": "600408", "company_name": "山西安泰集团股份有限公司", "announcement_date": "2024-04-26",
           "external_guarantee_balance": 0.0, "events": [
               {"event_type": "guarantee_provided", "relationship": "sister_company", "guarantor": "山西安泰集团股份有限公司",
                "guaranteed_party": "山西新泰钢铁有限公司", "guarantee_amount": 1, "guarantee_unit": "亿元",
                "end_date": "2024-06-20", "source_page": 2, "evidence_text": "x"},
               {"event_type": "guarantee_limit", "relationship": "sister_company", "guarantor": "山西安泰集团股份有限公司",
                "guaranteed_party": "山西新泰钢铁有限公司", "guarantee_amount": 1, "guarantee_unit": "亿元",
                "source_page": 2, "evidence_text": "x"},
               {"event_type": "guarantee_released", "relationship": "sister_company", "guarantor": "山西安泰集团股份有限公司",
                "guaranteed_party": "山西新泰钢铁有限公司", "source_page": 3, "evidence_text": "x"}]}
    edges, _ = edges_from(doc, "g.json")
    assert [(e.valid_from, e.valid_to) for e in edges] == [("2024-04-26", "2024-06-20"), ("2024-04-26", "2025-04-26")]
    signals = signals_from(doc, "g.json")
    assert signals[0].valid_to == "2024-06-20"


def test_maintenance_signal_ends_at_restart():
    doc = {"security_code": "600507", "company_name": "方大特钢科技股份有限公司", "announcement_date": "2026-05-09",
           "events": [{"event_type": "maintenance", "project_name": "检修", "capacity_changes": [],
                       "shutdown_start_date": "2026-05-10", "shutdown_days": 20, "source_page": 1, "evidence_text": "x"}]}
    (s,) = signals_from(doc, "m.json")
    assert (s.valid_from, s.valid_to) == ("2026-05-10", "2026-05-30")


def test_rows_without_dates_stay_in_force_and_legacy_rows_use_publication_date():
    assert is_active({}, "2026-01-01")
    assert is_active({"announcement_date": "2025-01-01"}, "2026-01-01")
    assert not is_active({"announcement_date": "2027-01-01"}, "2026-01-01")
