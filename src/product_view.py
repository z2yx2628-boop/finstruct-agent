"""企业档案 · 产品与价格: the product mix read as demand exposure (display only).

  product_rows  : each product's revenue share (with an 其他 row so the mix adds up to 100%), the futures contract
                  that tracks its price, the 20- and 60-day moves and where today's price sits in its history
  reading       : one sentence: which demand the company lives on (flat = manufacturing, long = property and
                  infrastructure) and how today's price move hits annual revenue
  peer_position : the flat / long share against the 24 core mills
  mix_history   : flat vs long share by year, from the same annual product breakdowns
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from statistics import median

from src.product_layer import exposure_as_of, exposure_table, products

ROOT = Path(__file__).resolve().parents[1]
PRICES = ROOT / "data" / "external" / "prices"
SYMBOL_CN = {"HC0": "热卷期货", "RB0": "螺纹期货", "I0": "铁矿石期货", "J0": "焦炭期货", "JM0": "焦煤期货"}
DEMAND = {"P_FLAT": "汽车、家电、船舶等制造业", "P_LONG": "房地产与基建", "P_SPECIAL": "机械、能源装备等高端制造",
          "P_PIPE": "油气、管网与建筑"}
CORE_PRODUCTS = ("P_FLAT", "P_LONG", "P_SPECIAL", "P_PIPE")


@lru_cache(maxsize=16)
def _series(symbol: str) -> tuple[tuple[str, float], ...]:
    path = PRICES / f"{symbol}.csv"
    if not path.exists():
        return ()
    with path.open(encoding="utf-8-sig", newline="") as f:
        return tuple((r["date"][:10], float(r["close"])) for r in csv.DictReader(f) if r.get("close"))


def price_stats(symbol: str, as_of: str) -> dict | None:
    rows = [(d, v) for d, v in _series(symbol) if d <= as_of]
    if len(rows) <= 60:
        return None
    last = rows[-1][1]
    hist = sorted(v for _, v in rows)
    return {"date": rows[-1][0], "close": last, "ret20": last / rows[-21][1] - 1, "ret60": last / rows[-61][1] - 1,
            "pct": sum(1 for v in hist if v <= last) / len(hist), "since": rows[0][0][:4]}


def product_rows(code: str, as_of: str) -> list[dict]:
    e = exposure_as_of(code, as_of)
    if not (e and e.get("products")):
        return []
    meta = {p["product_id"]: p for p in products()}
    out = []
    for pid, v in sorted(e["products"].items(), key=lambda kv: -(kv[1].get("share") or 0)):
        sym = meta.get(pid, {}).get("price_symbol") or ""
        stats = price_stats(sym, as_of) if sym else None
        out.append({"pid": pid, "产品": meta.get(pid, {}).get("name", pid), "share": v.get("share"),
                    "跟踪价格": f"{SYMBOL_CN.get(sym, sym)}（代表{meta.get(pid, {}).get('name', '').split('（')[0]}）" if sym else "—",
                    "stats": stats, "原文条目": v.get("items", ""), "下游需求": DEMAND.get(pid, "")})
    known = sum(r["share"] or 0 for r in out)
    if 0.005 < 1 - known < 0.5:
        out.append({"pid": "OTHER", "产品": "其他", "share": round(1 - known, 4), "跟踪价格": "—", "stats": None,
                    "原文条目": "年报中其他产品、贸易与服务等", "下游需求": ""})
    return out


def revenue_hit(rows: list[dict], annual_revenue_yi: float | None) -> float | None:
    """Annual revenue change if today's 20-day price moves held for a year (products with a tracked price only)."""
    if not annual_revenue_yi:
        return None
    hit = [annual_revenue_yi * r["share"] * r["stats"]["ret20"] for r in rows if r["share"] and r["stats"]]
    return sum(hit) if hit else None


def peer_shares(codes: list[str], as_of: str, pid: str) -> dict[str, float]:
    out = {}
    for c in codes:
        e = exposure_as_of(c, as_of) or {}
        s = (e.get("products", {}).get(pid) or {}).get("share")
        if s is not None:
            out[c] = s
    return out


def peer_position(code: str, codes: list[str], as_of: str, pid: str) -> dict | None:
    vals = peer_shares(codes, as_of, pid)
    if code not in vals or len(vals) < 3:
        return None
    order = sorted(vals, key=lambda c: -vals[c])
    return {"rank": order.index(code) + 1, "n": len(order), "median": median(vals.values()), "value": vals[code]}


def reading(rows: list[dict], hit_yi: float | None) -> str:
    main = [r for r in rows if r["pid"] in CORE_PRODUCTS and r["share"]]
    if not main:
        return ""
    top = main[0]
    text = f"收入的 {top['share']:.0%} 来自{top['产品']}，主要受{DEMAND[top['pid']]}需求驱动"
    long_ = next((r for r in main if r["pid"] == "P_LONG"), None)
    if top["pid"] == "P_FLAT":
        share = long_["share"] if long_ else 0
        text += f"；长材只占 {share:.0%}，对地产与基建的直接暴露{'较小' if share < 0.3 else '也不小'}"
    elif top["pid"] == "P_LONG":
        text += "，地产与基建走弱时首当其冲"
    if hit_yi is not None:
        text += f"。按近 20 日价格变动、若持续一年，年收入约{'减少' if hit_yi < 0 else '增加'} {abs(hit_yi):.1f} 亿元"
    return text + "。"


def mix_history(code: str) -> list[dict]:
    """Flat and long revenue shares by year (years with only an undivided 钢材 line are left out)."""
    rows = [r for r in exposure_table() if r["security_code"] == code and r["product_id"] in ("P_FLAT", "P_LONG")]
    names = {"P_FLAT": "板材", "P_LONG": "长材（建筑用钢）"}
    return [{"年度": r["period"][:4], "产品": names[r["product_id"]], "占收入": float(r["revenue_share"])}
            for r in sorted(rows, key=lambda r: r["period"])]
