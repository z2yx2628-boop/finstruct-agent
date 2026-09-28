"""Named counterparties from bond prospectuses: every row sourced to a file and page; group rows reach members."""
from src.prospectus_links import cross_group, for_company, rows


def test_rows_are_sourced():
    data = rows()
    assert len(data) >= 100
    assert all(r["source_file"].endswith(".pdf") and r["page"].isdigit() and r["counterparty"] for r in data)


def test_group_prospectus_reaches_listed_members():
    lg = for_company("600231", "2026-09-27")                 # 凌钢股份 is in the Ansteel group
    assert any(r["counterparty"] == "华晨汽车集团控股有限公司" for r in lg)
    assert any(r["counterparty"] == "黑龙江龙煤矿业集团股份有限公司" and r["related_party"] == "否" for r in cross_group(lg))


def test_not_used_before_balance_date():
    assert not [r for r in for_company("600231", "2024-06-30") if r["period"] >= "2024-12"]
