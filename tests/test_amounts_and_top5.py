"""Amounts in one unit, volumes kept apart, annual-report top-5 tables read in both exchange formats,
and relation persistence counting only years in which the relation happened."""
import re

from scripts.build_supply_relations import persistence
from scripts.extract_annual_top5 import ANON, tables, totals
from src.amounts import kind, to_wan


def test_money_is_converted_and_volume_never_is():
    assert to_wan("1,000,000", "元") == 100.0
    assert to_wan(3.5, "亿元") == 35000.0
    assert to_wan(60136990, "千元") == 6013699.0
    assert kind("吨") == "volume" and to_wan(352662, "吨") is None
    assert kind("万美元") == "foreign" and to_wan(10, "万美元") is None


def test_shenzhen_wording():
    flat = re.sub(r"\s+", "", """前五名客户合计销售金额（元）   8,285,549,959.63
        前五名客户合计销售金额占年度销售总额比例   8.22%
        前五名客户销售额中关联方销售额占年度销售总额比例   3.24%""")
    t = totals(flat, "customer")
    assert abs(t["top5_wan"] - 828555.0) < 0.01
    assert round(t["top5_share"], 4) == 0.0822 and round(t["related_share"], 4) == 0.0324


def test_shanghai_wording_across_line_breaks():
    flat = re.sub(r"\s+", "", """前五名供应商采购额981,021万元，占年度采购总额12.2%；其中前五名供应商采购额中关联方采
        购额515,624万元，占年度采购总额9.56%。""")
    t = totals(flat, "supplier")
    assert t["top5_wan"] == 981021.0 and round(t["top5_share"], 4) == 0.122
    assert t["related_wan"] == 515624.0 and round(t["related_share"], 4) == 0.0956


def test_tables_are_found_by_their_header_and_anonymous_names_are_marked():
    window = [(20, line) for line in """
        序号                  客户名称                         销售额（元）                 占年度销售总额比例
        1           客户 a                                   3,269,163,777.45                        3.24%
        2           客户 b                                   2,278,911,830.69                        2.26%
        合计                      --                         5,548,075,608.14                        5.50%
                                                 单位：亿元
        序号     供应商名称            采购额      占年度采购总额比例（%）
        1        华润（集团）有限公司    190.1        0.9
""".splitlines()]
    found = tables(window)
    rows, unit, _ = found["customer"]
    assert unit == "元" and [r["name"] for r in rows] == ["客户a", "客户b"]
    assert all(ANON.match(r["name"]) for r in rows)
    rows, unit, _ = found["supplier"]
    assert unit == "亿元" and rows[0]["name"] == "华润（集团）有限公司" and not ANON.match(rows[0]["name"])


def test_planned_caps_and_anonymous_rows_do_not_count_as_years():
    base = {"company_id": "000001", "direction": "upstream", "counterparty_key": "X"}
    rows = [dict(base, year="2023", amount_type="上年实际发生"), dict(base, year="2024", amount_type="上年实际发生"),
            dict(base, year="2025", amount_type="预计额度（上限）")]
    persistence(rows)
    assert rows[0]["years_seen"] == 2 and rows[0]["last_year"] == 2024 and rows[0]["run_years"] == 2


def test_a_wrapped_name_is_joined_and_a_repeated_header_is_skipped():
    lines = """       序号                    供应商名称                         采购额（元）              占年度采购总额比例
        3        国网辽宁省电力有限公司本溪供电公司                         3,155,866,088.46              6.53%
                 本溪钢铁（集团）矿业辽阳马耳岭球团有限
        4                                                  1,955,304,447.95              4.05%
                 公司
        序号                     供应商名称                     采购额（元）               占年度采购总额比例
        5        黑龙江龙煤矿业集团股份有限公司                           1,373,289,299.05              2.84%
       合计                           --                    24,134,103,555.48           49.93%""".splitlines()
    rows, unit, _ = tables([(1, line) for line in lines])["supplier"]
    assert unit == "元"
    assert [r["name"] for r in rows] == ["国网辽宁省电力有限公司本溪供电公司", "本溪钢铁（集团）矿业辽阳马耳岭球团有限公司",
                                         "黑龙江龙煤矿业集团股份有限公司"]


def test_two_year_totals_with_a_separate_unit_line():
    from scripts.extract_annual_top5 import totals_by_line
    lines = """  金额单位：人民币百万元
  2024 年度  2023 年度
前五名客户合计销售金额                         43,643                       45,235
前五名客户合计销售金额占年度
                                              41.52                        39.93
销售总额比例（%）
前五名客户销售额中关联方销售
                                              37.32                        39.93
额占年度销售总额比例（%）""".splitlines()
    t = totals_by_line(lines, "customer")
    assert t["top5_wan"] == 4364300.0 and round(t["top5_share"], 4) == 0.4152 and round(t["related_share"], 4) == 0.3732
