from src.product_layer import classify, exposure_from_composition


def test_items_are_classified_by_what_the_company_names():
    cases = {"中宽热带": "P_FLAT", "钢板": "P_FLAT", "板带材": "P_FLAT", "棒材": "P_LONG", "高线": "P_LONG",
             "型钢": "P_LONG", "不锈钢冷轧板": "P_SPECIAL", "铸管等产品": "P_PIPE", "焦炭加工及化产": "P_COKE",
             "钢材产品": "P_STEEL", "钢材、钢坯销售": "P_STEEL", "钢坯": "P_SEMI",
             "提供劳务": None, "其他(补充)": None, "整车业务": None}
    assert {k: classify(k) for k in cases} == cases


def test_latest_annual_product_breakdown_is_used():
    rows = [{"报告日期": "2025-12-31", "分类类型": "按产品分类", "主营构成": "棒材", "主营收入": "100", "收入比例": "0.6", "毛利率": "-0.06"},
            {"报告日期": "2025-12-31", "分类类型": "按产品分类", "主营构成": "中宽热带", "主营收入": "40", "收入比例": "0.24", "毛利率": "-0.05"},
            {"报告日期": "2025-12-31", "分类类型": "按产品分类", "主营构成": "其他", "主营收入": "5", "收入比例": "0.16", "毛利率": "0.1"}]
    e = exposure_from_composition(rows)
    assert e["period"] == "2025-12-31" and e["products"]["P_LONG"]["share"] == 0.6 and e["products"]["P_FLAT"]["share"] == 0.24
    assert e["unmapped_share"] == 0.16


def test_price_shock_section_always_carries_the_caveat():
    from src.price_shock import CAVEAT, report_section
    lines = report_section("2024-09-30", {})
    assert any(CAVEAT in line for line in lines)
    assert any("焦炭上涨" in line for line in lines)          # 20-day coke move on 2024-09-30 was +13%


def test_stress_index_is_transparent_and_refuses_missing_exposure():
    from src.price_shock import scenario_stress, stress_index
    assert stress_index(0.20, 0.60, "weak") == 12.0
    assert stress_index(-0.20, 0.60, "medium") == 6.0
    assert stress_index(0.20, None, "weak") is None
    rows = scenario_stress([{"name": "甲", "share": 0.6, "tier": "weak"},
                            {"name": "乙", "share": 0, "tier": "weak"}], 0.2)
    assert rows[0]["name"] == "甲" and rows[0]["stress_index"] == 12.0
    assert rows[1]["name"] == "乙" and not rows[1]["quantifiable"]
