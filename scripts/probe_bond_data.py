"""Feasibility probe for ⑬ (bond spread signal): which free bond data does akshare give on this machine?
Prints what each source returns; changes nothing. Run:  python scripts/probe_bond_data.py
"""
import traceback

import akshare as ak

PROBES = [
    ("中债收益率曲线（国债/企业债，按评级）", "bond_china_yield", dict(start_date="20260101", end_date="20260925")),
    ("银行间债券信息查询（按发行人：河钢集团）", "bond_info_cm", dict(bond_name="", bond_code="", bond_issue="河钢集团", bond_type="", coupon_type="", issue_year="", underwriter="", grade="")),
    ("沪深交易所债券日行情（示例代码）", "bond_zh_hs_daily", dict(symbol="sh163006")),
    ("沪深债券实时行情列表", "bond_zh_hs_spot", dict()),
]

for label, name, kwargs in PROBES:
    print(f"\n=== {label}: ak.{name}")
    fn = getattr(ak, name, None)
    if fn is None:
        print("  not available in this akshare version")
        continue
    try:
        df = fn(**kwargs)
        print(f"  rows={len(df)} columns={list(df.columns)[:12]}")
        print(df.head(5).to_string()[:1500])
    except Exception as e:  # noqa: BLE001
        print("  failed:", type(e).__name__, str(e)[:300])
        traceback.print_exc(limit=1)
