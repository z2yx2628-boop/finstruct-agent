"""Futures layer: steel-mill margins implied by futures prices, and companies' disclosed hedging.

Two parts, both SCENARIO / DESCRIPTIVE, not part of the fragility score:

1. 盘面利润 (futures-implied margin per tonne). Standard industry approximations
       螺纹盘面利润 = 螺纹 - 1.6 x 铁矿 - 0.5 x 焦炭        (元/吨钢, before processing and other costs)
       热卷盘面利润 = 热卷 - 1.6 x 铁矿 - 0.5 x 焦炭
       焦化盘面利润 = 焦炭 - 1.33 x 焦煤                    (元/吨焦, before processing costs)
   using main continuous contracts (RB0, HC0, I0, J0, JM0; data/external/prices). It is an
   industry-wide stress gauge, not any company's actual profit. Point in time: only prices on or
   before the evaluation date are used.
2. 套期保值 (hedging) disclosed in announcement titles (data/live/announcement_titles), split into
   commodity futures and FX. A hedging programme can partly cushion a raw-material shock; the cache
   covers only the newest pages of each company's list, so "not found" means "not in the cached
   titles", never "no hedging".

The pre-registered iron-ore shock test (docs/shock_transmission_preregistration.md) did not find a
significant effect, so nothing here enters the risk score.
"""
from __future__ import annotations

import csv
import re
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICES = ROOT / "data" / "external" / "prices"
TITLES = ROOT / "data" / "live" / "announcement_titles"

ORE_PER_T, COKE_PER_T, COAL_PER_COKE = 1.6, 0.5, 1.33
SINCE = "2014-01-01"            # iron-ore futures started trading in late 2013
WINDOW = 20                     # trading days for the "recent change" figures
CAVEAT = ("盘面利润用期货主力连续合约按行业通用系数估算（螺纹/热卷 − 1.6×铁矿 − 0.5×焦炭；焦炭 − 1.33×焦煤），"
          "未扣加工及其他成本，是全行业的压力指标，不是任何一家企业的实际利润。铁矿石冲击的预先登记检验未达显著，"
          "期货与套保信息只作情景和核查提示，不计入承压评分。")
NAMES = {"RB0": "螺纹钢", "HC0": "热轧卷板", "I0": "铁矿石", "J0": "焦炭", "JM0": "焦煤"}


@lru_cache(maxsize=None)
def series(symbol: str) -> tuple[tuple[str, ...], tuple[float, ...]]:
    path = PRICES / f"{symbol}.csv"
    if not path.exists():
        return (), ()
    days, close = [], []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                c = float(r["close"])
            except (TypeError, ValueError):
                continue
            if c > 0:
                days.append(r["date"][:10])
                close.append(c)
    return tuple(days), tuple(close)


def price_on(symbol: str, day: str) -> float | None:
    """Last close on or before `day`."""
    days, close = series(symbol)
    i = bisect_right(days, day)
    return close[i - 1] if i else None


def margin_formula(kind: str, p: dict[str, float]) -> float:
    if kind == "rebar":
        return p["RB0"] - ORE_PER_T * p["I0"] - COKE_PER_T * p["J0"]
    if kind == "hrc":
        return p["HC0"] - ORE_PER_T * p["I0"] - COKE_PER_T * p["J0"]
    if kind == "coke":
        return p["J0"] - COAL_PER_COKE * p["JM0"]
    raise ValueError(kind)


INPUTS = {"rebar": ("RB0", "I0", "J0"), "hrc": ("HC0", "I0", "J0"), "coke": ("J0", "JM0")}
LABEL = {"rebar": "螺纹钢吨钢盘面利润", "hrc": "热卷吨钢盘面利润", "coke": "焦化吨焦盘面利润"}


@lru_cache(maxsize=None)
def margin_series(kind: str) -> tuple[tuple[str, ...], tuple[float, ...]]:
    """Margin on every day all inputs traded (from SINCE)."""
    syms = INPUTS[kind]
    maps = [dict(zip(*series(s))) for s in syms]
    common = sorted(set.intersection(*(set(m) for m in maps)))
    days, vals = [], []
    for d in common:
        if d < SINCE:
            continue
        days.append(d)
        vals.append(margin_formula(kind, {s: m[d] for s, m in zip(syms, maps)}))
    return tuple(days), tuple(vals)


def percentile(value: float, history: list[float]) -> float | None:
    if not history:
        return None
    return sum(v <= value for v in history) / len(history)


def margin_snapshot(kind: str, as_of: str) -> dict | None:
    """Latest margin on or before as_of, its 20-day change split by input, and its historical percentile."""
    days, vals = margin_series(kind)
    i = bisect_right(days, as_of)
    if i <= WINDOW:
        return None
    day, now, base_day = days[i - 1], vals[i - 1], days[i - 1 - WINDOW]
    hist = list(vals[:i])
    last3 = [v for d, v in zip(days[:i], hist) if d >= f"{int(day[:4]) - 3}{day[4:]}"]
    syms = INPUTS[kind]
    now_p = {s: price_on(s, day) for s in syms}
    base_p = {s: price_on(s, base_day) for s in syms}
    coef = {"rebar": {"RB0": 1, "I0": -ORE_PER_T, "J0": -COKE_PER_T},
            "hrc": {"HC0": 1, "I0": -ORE_PER_T, "J0": -COKE_PER_T},
            "coke": {"J0": 1, "JM0": -COAL_PER_COKE}}[kind]
    contrib = [{"品种": NAMES[s], "合约": s, f"{WINDOW}日前价格": base_p[s], "最新价格": now_p[s],
                "价格变化": now_p[s] / base_p[s] - 1, "对利润的贡献（元/吨）": coef[s] * (now_p[s] - base_p[s])}
               for s in syms]
    return {"kind": kind, "label": LABEL[kind], "date": day, "value": now, "base_date": base_day,
            "change": now - vals[i - 1 - WINDOW], "pct_all": percentile(now, hist), "pct_3y": percentile(now, last3),
            "since": days[0], "min": min(hist), "max": max(hist), "contrib": contrib, "prices": now_p}


def scenario(kind: str, as_of: str, moves: dict[str, float]) -> dict | None:
    """Margin after hypothetical % moves of the inputs (e.g. {"I0": 0.10} = iron ore +10%)."""
    snap = margin_snapshot(kind, as_of)
    if snap is None:
        return None
    p = {s: v * (1 + moves.get(s, 0.0)) for s, v in snap["prices"].items()}
    new = margin_formula(kind, p)
    days, vals = margin_series(kind)
    hist = list(vals[:bisect_right(days, as_of)])
    return {"before": snap["value"], "after": new, "delta": new - snap["value"], "pct_after": percentile(new, hist),
            "prices_after": p}


# ---------------------------------------------------------------- hedging disclosed in announcement titles
HEDGE = re.compile(r"套期保值|套保|衍生品")
FX = re.compile(r"外汇|汇率|远期结售汇")
COMMODITY = re.compile(r"商品|期货|大宗")
POLICY = re.compile(r"制度|办法|准则|细则")


def classify(title: str) -> str | None:
    if not HEDGE.search(title):
        return None
    if FX.search(title) and not COMMODITY.search(title.replace("外汇衍生品", "")):
        return "外汇"
    if COMMODITY.search(title):
        return "商品期货"
    return "未写明品种"


def hedging(code: str, as_of: str, months: int = 15) -> dict:
    """Hedging announcements in the cached title list, published within `months` before as_of."""
    path = TITLES / f"{code}.csv"
    if not path.exists():
        return {"cache_from": None, "items": [], "commodity": False, "unspecified": False, "fx": False}
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["notice_date"][:10] <= as_of]
    y, m = int(as_of[:4]), int(as_of[5:7]) - months
    while m <= 0:
        y, m = y - 1, m + 12
    start = f"{y:04d}-{m:02d}{as_of[7:10]}"
    items = []
    for r in rows:
        kind = classify(r["title"])
        if kind and r["notice_date"][:10] >= start:
            items.append({"日期": r["notice_date"][:10], "类别": kind, "性质": "管理制度" if POLICY.search(r["title"]) else "业务公告",
                          "公告标题": r["title"], "source_url": r.get("source_url", "")})
    items.sort(key=lambda x: x["日期"], reverse=True)
    business = [x for x in items if x["性质"] == "业务公告"]
    return {"cache_from": min((r["notice_date"][:10] for r in rows), default=None), "items": items,
            "commodity": any(x["类别"] == "商品期货" for x in business),
            "unspecified": any(x["类别"] == "未写明品种" for x in business),
            "fx": any(x["类别"] == "外汇" for x in business)}


def hedge_label(h: dict) -> str:
    parts = [name for key, name in (("commodity", "商品期货"), ("unspecified", "套保（未写明品种）"), ("fx", "外汇")) if h.get(key)]
    if parts:
        return " + ".join(parts)
    if h["items"]:
        return "仅有管理制度"
    return "缓存中未见"


# ---------------------------------------------------------------- company level: purchased iron ore cost
def ore_cost_exposure(code: str, as_of: str, ore_move: float, equity_yuan: float | None = None) -> dict | None:
    """Extra annual cost if the iron-ore price moves by `ore_move`, from the company's own annual report.

    Uses the 铁矿石供应情况 table (data/reference/annual_iron_ore_supply.csv, A grade): purchased ore =
    domestic + imported purchases (total minus self-supplied, whose cost does not follow the market price),
    from the latest annual report public on as_of. A one-year, all-else-equal scenario: no pass-through to
    steel prices, no inventory or long-term contract effects, no hedging.
    """
    from src.policy_shock import ANNUAL_ORE, _read, usable_from
    own = [r for r in _read(ANNUAL_ORE) if r["company_id"] == code and r["check"] == "ok"
           and usable_from(f"{r['fy']}-12-31") <= as_of and r.get("total_wan")]
    if not own:
        return None
    r = max(own, key=lambda r: r["fy"])
    total = float(r["total_wan"])
    self_ = float(r["self_wan"]) if r.get("self_wan") else 0.0
    purchased_yi = (total - self_) / 1e4
    extra_yi = purchased_yi * ore_move
    return {"fy": r["fy"], "purchased_yi": purchased_yi, "extra_yi": extra_yi,
            "to_equity": extra_yi * 1e8 / equity_yuan if equity_yuan and equity_yuan > 0 else None,
            "equity_nonpositive": equity_yuan is not None and equity_yuan <= 0,
            "source": f"{r['fy']}年年报 第{r['page']}页（铁矿石供应情况）"}


# ---------------------------------------------------------------- company level: revenue that tracks steel futures
STEEL_FUTURE = {"RB0": "螺纹（长材）", "HC0": "热卷（板材）"}
ANNUALIZE = {"0331": 4.0, "0630": 2.0, "0930": 4.0 / 3.0, "1231": 1.0}


def steel_revenue_exposure(code: str, as_of: str) -> dict | None:
    """Share of revenue in products whose price is tracked by rebar / hot-rolled coil futures (B grade:
    the company's own product-mix disclosure), plus annualized revenue from the latest public period."""
    from src.product_layer import exposure_as_of, products
    exp = exposure_as_of(code, as_of)
    if not (exp and exp.get("products")):
        return None
    sym = {p["product_id"]: p["price_symbol"] for p in products()}
    shares = {}
    for pid, v in exp["products"].items():
        s = sym.get(pid)
        if s in STEEL_FUTURE and v.get("share"):
            shares[s] = shares.get(s, 0.0) + v["share"]
    if not shares:
        return None
    snaps = sorted(p.name for p in (ROOT / "data" / "snapshots").glob("*") if p.name <= as_of
                   and (p / "quarterly_metrics.csv").exists())
    revenue = period = None
    if snaps:
        with (ROOT / "data" / "snapshots" / snaps[-1] / "quarterly_metrics.csv").open(encoding="utf-8-sig", newline="") as f:
            row = next((r for r in csv.DictReader(f) if r["security_code"] == code), None)
        if row and row.get("revenue") and row.get("period"):
            period = row["period"]
            revenue = float(row["revenue"]) * ANNUALIZE.get(period[4:], 1.0)
    return {"shares": shares, "mix_period": exp.get("period", ""), "revenue_annual_yi": revenue / 1e8 if revenue else None,
            "revenue_period": period}


def company_scenario(ore: dict | None, steel: dict | None, ore_move: float, steel_move: float,
                     equity_yuan: float | None) -> dict:
    """One-year, all-else-equal effect on profit: revenue change on futures-tracked steel minus extra ore cost."""
    cost = ore["purchased_yi"] * ore_move if ore else None
    rev = None
    if steel and steel.get("revenue_annual_yi"):
        rev = steel["revenue_annual_yi"] * sum(steel["shares"].values()) * steel_move
    parts = [x for x in (rev, -cost if cost is not None else None) if x is not None]
    total = sum(parts) if parts else None
    return {"cost_yi": cost, "revenue_yi": rev, "profit_yi": total,
            "to_equity": total * 1e8 / equity_yuan if (total is not None and equity_yuan and equity_yuan > 0) else None}
