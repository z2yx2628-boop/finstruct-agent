"""企业档案 · 客户与供应商: concentration reading, service shares, source labels."""
from src.partner_view import concentration_bars, concentration_reading, share_cell, source_label


def _c(fy, side, top5, rel):
    return {"fy": fy, "side": side, "top5_share": top5, "related_share": rel}


def test_reading_flags_rising_dependence_on_the_group():
    conc = [_c("2024", "supplier", 0.389, 0.295), _c("2025", "supplier", 0.533, 0.489)]
    line = concentration_reading(conc)[0]
    assert "上升 14.4 个百分点" in line and "29.5% 升到 48.9%" in line and "高度依赖集团" in line


def test_small_related_share_is_not_called_high_dependence():
    line = concentration_reading([_c("2025", "customer", 0.192, 0.158)])[0]
    assert "高度" not in line and "比重不高" in line


def test_bars_split_related_and_other():
    rows = concentration_bars([_c("2025", "supplier", 0.5, 0.3), _c("2024", "customer", 0.2, None)])
    assert {(r["构成"], round(r["占比"], 2)) for r in rows} == {("关联方", 0.3), ("非关联方", 0.2), ("未区分", 0.2)}


def test_services_are_not_a_share_of_purchases_and_sources_are_readable():
    r = {"counterparty": "八钢公司之联营企业(其他劳务)", "relation": "关联采购（劳务）", "share": 0.7518,
         "share_basis": "占2024年年度采购总额", "share_method": "按财报计算", "source_type": "日常关联交易公告",
         "source": "analysis_077_600581_related_estimate.json 第5页（2025-03-08）"}
    share, basis = share_cell(r)
    assert share is None and "仅作量级参考" in basis and "75%" in basis
    assert source_label(r) == "日常关联交易公告（2025-03-08） 第5页"
    goods = dict(r, counterparty="宝武集团之联营企业(资材备件)", relation="关联采购", share=0.31)
    assert share_cell(goods)[0] == 0.31
