"""企业档案 · 产品与价格: the mix adds up, the reading names the demand, the revenue hit is share x move."""
from src import product_view as pv


def test_reading_names_the_demand_and_the_revenue_hit():
    rows = [{"pid": "P_FLAT", "产品": "板材", "share": 0.76, "stats": {"ret20": -0.04}},
            {"pid": "P_LONG", "产品": "长材（建筑用钢）", "share": 0.18, "stats": {"ret20": -0.034}}]
    hit = pv.revenue_hit(rows, 200.0)
    assert abs(hit - (200 * 0.76 * -0.04 + 200 * 0.18 * -0.034)) < 1e-9
    text = pv.reading(rows, hit)
    assert text.startswith("收入的 76% 来自板材") and "制造业" in text and "长材只占 18%" in text and "减少" in text


def test_special_steel_does_not_talk_about_long_products():
    text = pv.reading([{"pid": "P_SPECIAL", "产品": "特钢与不锈钢", "share": 0.92, "stats": None}], None)
    assert "长材" not in text and "高端制造" in text


def test_mix_gets_an_other_row(monkeypatch):
    monkeypatch.setattr(pv, "exposure_as_of", lambda code, as_of: {"products": {"P_FLAT": {"share": 0.7, "items": "热轧"},
                                                                             "P_LONG": {"share": 0.2, "items": "螺纹"}}})
    monkeypatch.setattr(pv, "price_stats", lambda sym, as_of: None)
    rows = pv.product_rows("X", "2026-11-18")
    assert rows[-1]["产品"] == "其他" and abs(sum(r["share"] for r in rows) - 1) < 1e-9
