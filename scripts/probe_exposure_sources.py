"""Read-only probe (2026-09-27): can this network reach the two sources the product layer needs?

1. Business composition by product (东方财富 主营构成, akshare stock_zygc_em): what each company sells.
2. Daily prices of the chain's key products (新浪 futures main contracts): the shocks.

    python scripts/probe_exposure_sources.py
Writes nothing except data/external/probe/exposure_probe_*.csv samples, and prints what worked.
"""
import sys
import time
from pathlib import Path

import akshare as ak

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external" / "probe"
OUT.mkdir(parents=True, exist_ok=True)
SAMPLES = {"SH600019": "宝钢股份（板材为主）", "SZ000932": "华菱钢铁", "SH600231": "凌钢股份（长材较多）",
           "SH600408": "安泰集团（焦炭，上游）", "SH600104": "上汽集团（汽车，下游）"}
FUTURES = {"J0": "焦炭", "JM0": "焦煤", "I0": "铁矿石", "RB0": "螺纹钢", "HC0": "热轧卷板"}

ok = {"composition": 0, "prices": 0}
print("== 1. 主营构成（东方财富 emweb）")
for code, label in SAMPLES.items():
    try:
        df = ak.stock_zygc_em(symbol=code)
        df.to_csv(OUT / f"exposure_probe_zygc_{code}.csv", index=False, encoding="utf-8-sig")
        dates = sorted(df["报告日期"].astype(str).unique()) if "报告日期" in df else []
        latest = df[df["报告日期"].astype(str) == dates[-1]] if dates else df
        by_product = latest[latest["分类类型"].astype(str).str.contains("产品")] if "分类类型" in latest else latest
        print(f"[ok]   {code} {label}: {len(df)} 行，报告期 {dates[0] if dates else '?'} … {dates[-1] if dates else '?'}")
        cols = [c for c in ("主营构成", "主营收入", "收入比例", "毛利率") if c in by_product]
        print(by_product[cols].head(6).to_string(index=False))
        ok["composition"] += 1
    except Exception as error:
        print(f"[fail] {code} {label}: {type(error).__name__}: {str(error)[:120]}")
    time.sleep(1.5)

print("\n== 2. 产品价格（新浪期货主力连续）")
for symbol, label in FUTURES.items():
    try:
        df = ak.futures_zh_daily_sina(symbol=symbol)
        df.to_csv(OUT / f"exposure_probe_price_{symbol}.csv", index=False, encoding="utf-8-sig")
        print(f"[ok]   {symbol} {label}: {len(df)} 天，{df['date'].iloc[0]} … {df['date'].iloc[-1]}，最新收盘 {df['close'].iloc[-1]}")
        ok["prices"] += 1
    except Exception as error:
        print(f"[fail] {symbol} {label}: {type(error).__name__}: {str(error)[:120]}")
    time.sleep(1.0)

print(f"\n主营构成 {ok['composition']}/{len(SAMPLES)} 成功；产品价格 {ok['prices']}/{len(FUTURES)} 成功")
sys.exit(0)
