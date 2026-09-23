from src.overseas_revenue import derive_shares, validate_row

BASE = {"unit": "亿元", "source_report": "2024年年度报告", "source_page": "35",
        "eu_disclosure": ""}


def test_empty_template_row_is_valid():
    assert validate_row({"security_code": "600019", "unit": ""}) == []


def test_filled_row_needs_source_and_consistent_totals():
    row = {**BASE, "total_revenue": "100", "domestic_revenue": "80",
           "overseas_revenue": "30", "source_page": ""}
    problems = validate_row(row)
    assert any("source_page" in p for p in problems)
    assert any(">2%" in p for p in problems)


def test_eu_revenue_requires_disclosure_flag():
    row = {**BASE, "total_revenue": "100", "overseas_revenue": "20", "eu_revenue": "5"}
    assert any("eu_disclosure" in p for p in validate_row(row))
    row["eu_disclosure"] = "europe_region"
    assert validate_row(row) == []


def test_derive_shares_from_domestic():
    out = derive_shares({**BASE, "total_revenue": "1,000", "domestic_revenue": "850",
                         "eu_revenue": "30", "eu_disclosure": "explicit_eu"})
    assert out["overseas_revenue"] == "150.00"
    assert out["overseas_share"] == "0.1500"
    assert out["eu_share"] == "0.0300"
