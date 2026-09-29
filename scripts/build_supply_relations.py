"""One table of named trading relations with amount, share and persistence:
data/reference/supply_relations.csv

Sources (all A-grade: the document names both parties and the number):
  1. 日常关联交易公告   data/chain/{live,*_fix1}/edges.csv, supply/service edges; the issuer is always one end.
                       Each announcement gives next year's cap (预计额度) and usually last year's actual (上年实际).
  2. 债券募集说明书     data/reference/prospectus_links.csv (run scripts/enrich_prospectus_links.py first):
                       top-5 suppliers/customers (amounts) and top-5 receivables/prepayments/payables (balances).
  3. 年报前五名客户/供应商  data/reference/annual_top5.csv, when present (scripts/extract_annual_top5.py).

For every row:
  amount_wan / amount_yi   money only, in one unit (src/amounts.py); volumes go to quantity / quantity_unit
  share, share_basis, share_method
      原表披露   the percentage printed in the source table (its column header is share_basis)
      按财报计算  amount / the company's own revenue (customers) or operating cost (suppliers, 采购额近似)
                 for the same year: listed companies from the Sina financial abstract, groups from
                 data/reference/relation_denominators.csv (prospectus financial statements, page cited)
      空          no sensible denominator (e.g. a balance without its item total)
  years_seen, first_year, last_year, run_years   over ALL sources, per (company, direction, counterparty):
      how many distinct years the relation appears, and the longest run of consecutive years ending at last_year

    python scripts/build_supply_relations.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.amounts import to_wan  # noqa: E402
from src.quarterly import parse_abstract  # noqa: E402

OUT = ROOT / "data" / "reference" / "supply_relations.csv"
CHAINS = ["data/chain/live", "data/chain/analysis_v1_fix1", "data/chain/backtest_antai_fix1", "data/chain/backtest_linggang_fix1"]
PROSPECTUS = ROOT / "data" / "reference" / "prospectus_links.csv"
TOP5 = ROOT / "data" / "reference" / "annual_top5.csv"
DENOM = ROOT / "data" / "reference" / "relation_denominators.csv"
CONC = ROOT / "data" / "reference" / "annual_concentration.csv"    # scripts/extract_annual_top5.py
PLANNED = "预计额度（上限）"   # a cap for next year: never counted as a year in which the relation happened
QDIR = ROOT / "data" / "external" / "financials" / "quarterly"
ROLE = {"supplier": ("upstream", "供应商", "采购额"), "customer": ("downstream", "客户", "销售额"),
        "receivable": ("downstream", "应收账款（对方欠款）", "期末余额"), "contract_liability": ("downstream", "合同负债（对方预付）", "期末余额"),
        "prepayment": ("upstream", "预付款项（预付给对方）", "期末余额"), "payable": ("upstream", "应付账款（欠对方）", "期末余额")}
FIELDS = ["company_id", "company_name", "direction", "relation", "counterparty", "counterparty_key", "counterparty_code", "related_party", "year",
          "period", "amount_type", "amount_wan", "amount_yi", "quantity", "quantity_unit", "share", "share_basis", "share_method",
          "years_seen", "first_year", "last_year", "run_years", "goods", "source_type", "source", "grade", "available_from",
          "counterparty_named"]


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm(name: str) -> str:
    n = re.sub(r"\s+", "", name or "").replace("(", "（").replace(")", "）")
    return re.sub(r"(股份)?有限(责任)?公司$", "", n)


_fin: dict[str, dict] = {}


def annual(code: str) -> dict[str, dict]:
    """year -> {revenue_wan, cost_wan} from the Sina abstract (cost = revenue x (1 - gross margin))."""
    if code not in _fin:
        path = QDIR / f"{code}_abstract.csv"
        out = {}
        if path.exists():
            with path.open(encoding="utf-8-sig", newline="") as f:
                periods = parse_abstract(list(csv.reader(f)))
            for p, m in periods.items():
                if p.endswith("1231") and m.get("revenue"):
                    rev = m["revenue"] / 1e4
                    gm = m.get("gross_margin")
                    out[p[:4]] = {"revenue_wan": rev, "cost_wan": rev * (1 - gm) if gm is not None else None,
                                  "source": "新浪财务摘要（营业总收入；营业成本 = 收入 ×（1 − 毛利率））"}
        for c in read(CONC):   # the real annual sales / purchase totals printed in the annual report (top-5 section)
            if c["company_id"] == code and c.get("total_wan"):
                slot = out.setdefault(c["fy"], {"revenue_wan": None, "cost_wan": None, "source": ""})
                key = "sales_total_wan" if c["side"] == "customer" else "purchase_total_wan"
                slot[key] = float(c["total_wan"])
                slot[key + "_source"] = f"{c['fy']}年年报 第{c['page']}页（前五名{('客户销售额' if c['side'] == 'customer' else '供应商采购额')} ÷ 其占比）"
        for d in read(DENOM):
            if d["entity_id"] == code:
                out[d["year"]] = {"revenue_wan": float(d["revenue_wan"]) if d["revenue_wan"] else None,
                                  "cost_wan": float(d["cost_wan"]) if d["cost_wan"] else None,
                                  "source": f"{d['source']} 第{d['page']}页"}
        _fin[code] = out
    return _fin[code]


def computed_share(company: str, year: str, direction: str, amount_wan: float | None, estimate: bool = False):
    """(share, basis) against the company's own revenue (sales) or operating cost (purchases)."""
    if amount_wan is None:
        return None, ""
    fin = annual(company)
    base_year = str(int(year) - 1) if estimate else year
    f = fin.get(base_year)
    if not f:
        return None, ""
    if direction == "downstream":
        key, label = ("sales_total_wan", "年度销售总额") if f.get("sales_total_wan") else ("revenue_wan", "营业收入")
    else:
        key, label = (("purchase_total_wan", "年度采购总额") if f.get("purchase_total_wan")
                      else ("cost_wan", "营业成本（采购额近似）"))
    if not f.get(key):
        return None, ""
    prefix = (f"预计额度占{base_year}年{label}" if estimate else f"占{base_year}年{label}")
    return amount_wan / f[key], prefix


def from_announcements() -> list[dict]:
    rows, seen = [], set()
    for chain in CHAINS:
        for e in read(ROOT / chain / "edges.csv"):
            if e["edge_type"] not in ("supply", "service") or not e.get("issuer_id"):
                continue
            sells = e["src_id"] == e["issuer_id"]
            direction = "downstream" if sells else "upstream"
            cp_name = e["dst_name"] if sells else e["src_name"]
            cp_id = e["dst_id"] if sells else e["src_id"]
            key = (e["issuer_id"], direction, norm(cp_name), e["period"], e["category_text"], e["amount_wan"], e["prior_actual_wan"])
            if key in seen:
                continue
            seen.add(key)
            base = {"cp_key": cp_id if cp_id and not cp_id.startswith("N_") else "", "company_id": e["issuer_id"], "company_name": e["src_name"] if sells else e["dst_name"], "direction": direction,
                    "relation": ("关联销售" if sells else "关联采购") + ("（劳务）" if e["edge_type"] == "service" else ""),
                    "counterparty": cp_name, "counterparty_code": cp_id if re.fullmatch(r"\d{6}", cp_id or "") else "",
                    "related_party": "是", "goods": e["category_text"], "source_type": "日常关联交易公告",
                    "source": f"{e['source_doc'].split('/')[-1]} 第{e['source_page']}页（{e['announcement_date']}）", "grade": "A",
                    "available_from": e["announcement_date"]}
            period = e["period"]
            if e["amount_wan"] and period:
                amt = float(e["amount_wan"])
                share, basis = computed_share(e["issuer_id"], period, direction, amt, estimate=True)
                rows.append(dict(base, year=period, period=period, amount_type="预计额度（上限）", amount_wan=amt, share=share,
                                 share_basis=basis, share_method="按财报计算" if share is not None else ""))
            if e["prior_actual_wan"] and period and float(e["prior_actual_wan"]) > 0:
                amt, year = float(e["prior_actual_wan"]), str(int(period) - 1)
                share, basis = computed_share(e["issuer_id"], year, direction, amt)
                rows.append(dict(base, year=year, period=year, amount_type="上年实际发生", amount_wan=amt, share=share,
                                 share_basis=basis, share_method="按财报计算" if share is not None else ""))
    return rows


def from_prospectus() -> list[dict]:
    rows = []
    for r in read(PROSPECTUS):
        if r["role"] not in ROLE:
            continue
        direction, relation, amount_type = ROLE[r["role"]]
        year = (r["period"] or "")[:4]
        volume = r.get("amount_kind") == "volume"
        amount_wan = float(r["amount_wan"]) if r.get("amount_wan") else to_wan(r["amount"], r["unit"])
        share, basis, method = (float(r["share"]), r["share_basis"], "原表披露") if r.get("share") else (None, "", "")
        full_year = (r["period"] or "").endswith("-12")
        if share is None and r["role"] in ("supplier", "customer") and full_year:
            share, basis = computed_share(r["issuer_id"], year, direction, amount_wan)
            method = "按财报计算" if share is not None else ""
        rows.append({"company_id": r["issuer_id"], "company_name": r["issuer"], "direction": direction, "relation": relation,
                     "counterparty": r["counterparty"], "counterparty_code": r["counterparty_code"],
                     "related_party": r["related_party"], "year": year, "period": r["period"],
                     "amount_type": "销量" if volume else amount_type, "amount_wan": None if volume else amount_wan,
                     "quantity": r["quantity"] if volume else "", "quantity_unit": r["quantity_unit"] if volume else "",
                     "share": share, "share_basis": basis, "share_method": method, "goods": r.get("product_id", ""),
                     "source_type": "债券募集说明书", "source": f"{r['source_title']} 第{r['page']}页", "grade": "A",
                     "available_from": f"{r['period']}-01" if r["period"] else ""})
    return rows


def from_top5() -> list[dict]:
    return [dict(r, amount_wan=float(r["amount_wan"]) if r.get("amount_wan") else None,
                 share=float(r["share"]) if r.get("share") else None) for r in read(TOP5)]


def link_names(rows: list[dict]) -> None:
    """Give every row a `counterparty_key`: one key per counterparty of a company, so that an abbreviation in one
    announcement (赤峰九联) and the full name in another (赤峰九联煤化有限责任公司) count as the same relation.
    Rules: the same resolved entity id; or one normalised name (>= 4 characters) contained in the other."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["company_id"], r["direction"]), []).append(r)
    for members in groups.values():
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.setdefault(x, x) != x:
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        names = sorted({norm(r["counterparty"]) for r in members}, key=len)
        for r in members:
            find(norm(r["counterparty"]))
            if r.get("cp_key"):
                union("id:" + r["cp_key"], norm(r["counterparty"]))
        for i, a in enumerate(names):
            if len(a) < 4:
                continue
            for b in names[i + 1:]:
                if a in b:
                    union(a, b)
        clusters: dict[str, list[str]] = {}
        for n in names:
            clusters.setdefault(find(n), []).append(n)
        label = {root: max(ns, key=len) for root, ns in clusters.items()}
        for r in members:
            r["counterparty_key"] = label[find(norm(r["counterparty"]))]


def persistence(rows: list[dict]) -> None:
    """Years in which the relation actually happened (actual amounts, balances, volumes); next year's cap is a plan."""
    years: dict[tuple, set[int]] = {}
    for r in rows:
        if r["year"] and r["amount_type"] != PLANNED and r.get("counterparty_named", "Y") != "N":
            years.setdefault((r["company_id"], r["direction"], r["counterparty_key"]), set()).add(int(r["year"]))
    for r in rows:
        ys = years.get((r["company_id"], r["direction"], r["counterparty_key"]), set())
        if not ys:
            continue
        last, run = max(ys), 1
        while last - run in ys:
            run += 1
        r.update(years_seen=len(ys), first_year=min(ys), last_year=last, run_years=run)


def dedupe(rows: list[dict]) -> list[dict]:
    """The same figure quoted by two announcements (e.g. last year's actual repeated in a revised estimate) counts once."""
    seen, out = set(), []
    for r in rows:
        key = (r["company_id"], r["direction"], r["counterparty_key"], r["year"], r["amount_type"], r.get("goods", ""),
               r.get("amount_wan"), r.get("quantity", ""))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def main() -> None:
    rows = from_announcements() + from_prospectus() + from_top5()
    link_names(rows)
    rows = dedupe(rows)
    persistence(rows)
    for r in rows:
        r["amount_yi"] = "" if r.get("amount_wan") in (None, "") else f"{float(r['amount_wan']) / 1e4:.4f}"
        r["amount_wan"] = "" if r.get("amount_wan") in (None, "") else f"{float(r['amount_wan']):.2f}"
        r["share"] = "" if r.get("share") in (None, "") else f"{float(r['share']):.4f}"
    rows.sort(key=lambda r: (r["company_id"], r["direction"], r["counterparty"], r["year"], r["amount_type"]))
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(f"{len(rows)} rows -> {OUT.relative_to(ROOT)}")
    print("by source:", dict(Counter(r["source_type"] for r in rows)))
    print("share:", dict(Counter(r["share_method"] or "无" for r in rows)))
    print("volume rows:", sum(1 for r in rows if r.get("quantity")))
    multi = {(r["company_id"], r["direction"], r["counterparty_key"]) for r in rows if int(r.get("years_seen") or 0) >= 3}
    print("relations seen in >= 3 years:", len(multi))


if __name__ == "__main__":
    main()
