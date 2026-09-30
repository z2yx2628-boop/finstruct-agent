"""Policy-shock scenarios (政策冲击库): carbon cost (EU CBAM / domestic ETS), export rebate or tariff
changes, and production cuts. Company-level, transparent, parameterised; SCENARIO ONLY, never scored.

Every number comes from a named source or is an explicit, user-adjustable assumption:
  * overseas revenue share  : the annual report's own 分地区 revenue rows with page (A, scripts/extract_annual_trade.py);
                              otherwise 东方财富主营构成“按地区分类” (B); point-in-time either way
  * CO2 intensity by route  : worldsteel Sustainability Indicators 2025 (2024 data): BF-BOF 2.34, scrap-EAF 0.69,
                              DRI-EAF 1.47 t CO2 / t crude steel (industry averages, not company data -> C)
  * production route        : data/reference/mill_routes.csv; unverified rows default to BF-BOF and are flagged
  * CBAM factor by year     : Directive 2003/87/EC Art. 10a(1a) phase-out of free allocation (2026 2.5% ... 2034 100%)
  * steel price             : 热卷主力合约 HC0 close on the evaluation date (元/吨)
  * carbon prices           : user inputs (no default is claimed to be a market quote)
Overseas revenue is not EU revenue: for CBAM the result is an upper bound of exposure. The index
reuses price_shock.stress_index (|cost as share of revenue| x exposed share x fragility buffer x 100).
"""
from __future__ import annotations

import csv
from pathlib import Path

from src.price_shock import TIER_WEIGHT, stress_index
from src.product_layer import ROOT

RAW = ROOT / "data" / "external" / "exposure" / "raw"
ROUTES = ROOT / "data" / "reference" / "mill_routes.csv"
INTENSITY = {"BF-BOF": 2.34, "EAF": 0.69, "DRI-EAF": 1.47}          # worldsteel 2025 report, 2024 data
CBAM_FACTOR = {2026: 0.025, 2027: 0.05, 2028: 0.10, 2029: 0.225, 2030: 0.485, 2031: 0.61, 2032: 0.735,
               2033: 0.86, 2034: 1.0}
KINDS = {"carbon": "碳成本（欧盟 CBAM / 国内碳市场）", "export": "出口退税、关税或反倾销", "cut": "限产"}
SOURCES = {
    "overseas": "年报“营业收入分地区”行（A 级，附页码；scripts/extract_annual_trade.py），缺失时用东方财富主营构成·按地区分类（B 级）；境外≠欧盟",
    "intensity": "worldsteel Sustainability Indicators 2025（2024 年行业平均：长流程 2.34、废钢电炉 0.69 t CO₂/t 粗钢，C 级）",
    "cbam": "欧盟排放交易指令 2003/87/EC 第 10a(1a) 条：CBAM 系数 2026 年 2.5%，逐年提高至 2034 年 100%",
    "price": "热卷主力合约 HC0 收盘价（评估日）",
}


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def usable_from(report_date: str) -> str:
    """Annual reports (12-31) are used only after 04-30 of the next year, as elsewhere in the project."""
    return f"{int(report_date[:4]) + 1}-04-30"


ANNUAL_OVERSEAS = ROOT / "data" / "reference" / "annual_overseas_revenue.csv"
ANNUAL_ORE = ROOT / "data" / "reference" / "annual_iron_ore_supply.csv"


def overseas_share(code: str, as_of: str) -> dict | None:
    """Latest annual overseas revenue share known on as_of: {'share', 'period', 'items', 'grade', 'source'} or None.
    The annual report itself (A, with page) first; the Eastmoney breakdown (B) when the report's table was not read."""
    own = [r for r in _read(ANNUAL_OVERSEAS) if r["company_id"] == code and r["check"] in ("ok", "only_domestic_reported")
           and r.get("overseas_share") not in (None, "") and usable_from(f"{r['fy']}-12-31") <= as_of]
    b = _eastmoney_share(code, as_of)
    if own:
        r = max(own, key=lambda r: r["fy"])
        if not b or f"{r['fy']}-12-31" >= b["period"]:          # the newest year wins; A before B within a year
            return {"share": float(r["overseas_share"]), "period": f"{r['fy']}-12-31",
                    "items": r.get("overseas_labels") or "（仅境内）", "grade": "A", "source": f"{r['fy']}年年报 第{r['page']}页"}
    return dict(b, grade="B", source="东方财富主营构成·按地区分类") if b else None


def iron_ore_import(code: str, as_of: str) -> dict | None:
    """Share of iron ore IMPORTED (by tonnes and by money) from the annual report's 铁矿石供应情况 table (A)."""
    own = [r for r in _read(ANNUAL_ORE) if r["company_id"] == code and r["check"] == "ok"
           and usable_from(f"{r['fy']}-12-31") <= as_of]
    if not own:
        return None
    r = max(own, key=lambda r: r["fy"])
    f = lambda k: float(r[k]) if r.get(k) not in (None, "") else None  # noqa: E731
    return {"fy": r["fy"], "import_share_t": f("import_share_t"), "import_share_amount": f("import_share_amount"),
            "import_t": f("import_t"), "total_t": f("total_t"), "import_wan": f("import_wan"),
            "source": f"{r['fy']}年年报 第{r['page']}页（铁矿石供应情况）"}


def _eastmoney_share(code: str, as_of: str) -> dict | None:
    rows = [r for r in _read(RAW / f"{code}.csv") if r.get("分类类型") == "按地区分类"
            and r["报告日期"].endswith("12-31") and usable_from(r["报告日期"]) <= as_of]
    if not rows:
        return None
    period = max(r["报告日期"] for r in rows)
    latest = [r for r in rows if r["报告日期"] == period]
    abroad = [r for r in latest if any(k in r["主营构成"] for k in ("境外", "国外", "海外", "出口"))]
    if not abroad:
        return None
    share = sum(float(r["收入比例"] or 0) for r in abroad)
    return {"share": round(share, 4), "period": period, "items": "、".join(r["主营构成"] for r in abroad)}


def routes() -> dict[str, dict]:
    return {r["security_code"]: r for r in _read(ROUTES)}


def route_of(code: str) -> tuple[str, bool]:
    r = routes().get(code)
    if r and r.get("route") in INTENSITY:
        return r["route"], r.get("verified") == "Y"
    return "BF-BOF", False


def steel_price(as_of: str, symbol: str = "HC0") -> float | None:
    rows = [r for r in _read(ROOT / "data" / "external" / "prices" / f"{symbol}.csv") if r["date"][:10] <= as_of and r.get("close")]
    return float(rows[-1]["close"]) if rows else None


def carbon_cost_per_ton(route: str, eu_price: float, year: int, domestic_price: float = 0.0,
                        domestic_gap: float = 0.0) -> dict:
    """元 per tonne of steel: CBAM part = intensity x EU price x CBAM factor (minus the domestic price already paid,
    simplified); domestic part = intensity x domestic price x allowance gap (currently capped near 3%)."""
    intensity = INTENSITY[route]
    factor = CBAM_FACTOR.get(year, 1.0 if year > 2034 else 0.0)
    cbam = max(0.0, intensity * factor * (eu_price - domestic_price))
    domestic = intensity * domestic_price * domestic_gap
    return {"intensity": intensity, "cbam_factor": factor, "cbam": round(cbam, 1), "domestic": round(domestic, 1)}


def carbon(fragility: dict[str, dict], as_of: str, eu_price: float, year: int, domestic_price: float = 0.0,
           domestic_gap: float = 0.03) -> list[dict]:
    price = steel_price(as_of)
    rows = []
    for code, f in fragility.items():
        if f.get("peer_group") != "core":
            continue
        route, verified = route_of(code)
        cost = carbon_cost_per_ton(route, eu_price, year, domestic_price, domestic_gap)
        exp = overseas_share(code, as_of)
        cbam_ratio = cost["cbam"] / price if price else None
        dom_ratio = cost["domestic"] / price if price else None
        cbam_idx = stress_index(cbam_ratio, exp["share"], f.get("tier", "")) if exp and cbam_ratio else None
        dom_idx = stress_index(dom_ratio, 1.0, f.get("tier", "")) if dom_ratio else None
        rows.append({"code": code, "name": f["security_name"], "tier": f.get("tier", ""), "route": route,
                     "route_verified": verified, "overseas_share": exp["share"] if exp else None,
                     "overseas_source": f"{exp['source']}（{exp['grade']}）" if exp else "",
                     "period": exp["period"] if exp else "", "cbam_per_ton": cost["cbam"], "domestic_per_ton": cost["domestic"],
                     "cbam_index": cbam_idx, "domestic_index": dom_idx,
                     "index": round((cbam_idx or 0) + (dom_idx or 0), 2) if (cbam_idx or dom_idx) else None})
    return sorted(rows, key=lambda r: (r["index"] is None, -(r["index"] or 0), r["name"]))


def export_change(fragility: dict[str, dict], as_of: str, change: float) -> list[dict]:
    """change = rebate cut or extra tariff as a share of export revenue (e.g. 0.05 = 5%)."""
    rows = []
    for code, f in fragility.items():
        if f.get("peer_group") != "core":
            continue
        exp = overseas_share(code, as_of)
        idx = stress_index(change, exp["share"], f.get("tier", "")) if exp else None
        rows.append({"code": code, "name": f["security_name"], "tier": f.get("tier", ""),
                     "overseas_share": exp["share"] if exp else None, "period": exp["period"] if exp else "",
                     "overseas_source": f"{exp['source']}（{exp['grade']}）" if exp else "", "index": idx})
    return sorted(rows, key=lambda r: (r["index"] is None, -(r["index"] or 0), r["name"]))


def production_cut(fragility: dict[str, dict], codes: list[str], cut: float) -> list[dict]:
    """A cut of `cut` of output at the chosen mills: revenue share at risk = cut (whole company exposed)."""
    rows = [{"code": c, "name": fragility[c]["security_name"], "tier": fragility[c].get("tier", ""),
             "cut": cut, "index": stress_index(cut, 1.0, fragility[c].get("tier", ""))} for c in codes if c in fragility]
    return sorted(rows, key=lambda r: -(r["index"] or 0))


def buffer_of(tier: str) -> float:
    return TIER_WEIGHT.get(tier, 0.5)
