"""All A-share steel companies (新浪行业“钢铁行业”; 东方财富行业板块 as fallback), compared with the project's 42 companies.

Writes data/manifests/steel_all_listed.csv (every constituent, with in_universe = Y/N) and adds the ones outside the
42 to data/manifests/extension_universe.csv as layer steel_other (verified = N). Those are covered WITHOUT any LLM
extraction: financials, prices and a fragility score against the 24 core mills (scripts/score_extension.py),
credit events from announcement titles (scripts/scan_credit_events.py), revenue by region (东方财富 主营构成).

    python scripts/list_steel_listed.py
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_financials import universe  # noqa: E402

OUT = ROOT / "data" / "manifests" / "steel_all_listed.csv"
EXT = ROOT / "data" / "manifests" / "extension_universe.csv"
BOARDS = ["钢铁行业", "钢铁"]


def fetch() -> tuple[list[tuple[str, str]], str]:
    """新浪行业“钢铁行业” first (the Sina site is reachable from the project network, as for announcements);
    东方财富行业板块 as a fallback (its push2 servers often refuse connections from outside mainland China)."""
    import akshare as ak
    try:
        sectors = ak.stock_sector_spot(indicator="新浪行业")
        name_col = next(c for c in sectors.columns if "板块" in str(c))
        label_col = next(c for c in sectors.columns if "label" in str(c).lower())
        hit = sectors[sectors[name_col].astype(str).str.contains("钢铁")]
        for label, board in zip(hit[label_col], hit[name_col]):
            df = ak.stock_sector_detail(sector=str(label))
            code_col = "code" if "code" in df.columns else next(c for c in df.columns if "代码" in str(c))
            nm_col = "name" if "name" in df.columns else next(c for c in df.columns if "名称" in str(c))
            rows = [(str(c).zfill(6)[-6:], str(n)) for c, n in zip(df[code_col], df[nm_col])]
            if rows:
                return rows, f"akshare {ak.__version__} 新浪行业「{board}」（{label}），{date.today()}"
    except Exception as error:  # noqa: BLE001
        print(f"  新浪行业: {type(error).__name__}: {str(error)[:80]}")
    for board in BOARDS:
        try:
            df = ak.stock_board_industry_cons_em(symbol=board)
        except Exception as error:  # noqa: BLE001
            print(f"  东方财富 {board}: {type(error).__name__}")
            continue
        code_col = next(c for c in df.columns if "代码" in str(c))
        name_col = next(c for c in df.columns if "名称" in str(c))
        rows = [(str(c).zfill(6), str(n)) for c, n in zip(df[code_col], df[name_col])]
        if rows:
            return rows, f"akshare {ak.__version__} stock_board_industry_cons_em('{board}')，{date.today()}"
    sys.exit("没有取到钢铁行业成分股：新浪和东方财富都连不上，稍后重试。")


def main() -> None:
    rows, source = fetch()
    ours = {m["security_code"]: m for m in universe()}
    with EXT.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields, ext = reader.fieldnames, list(reader)
    known = {m["security_code"] for m in ext}
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["security_code", "security_name", "in_universe", "tier", "segment", "source"])
        for code, name in sorted(rows):
            m = ours.get(code)
            w.writerow([code, name, "Y" if m else "N", m["tier"] if m else "", m["segment"] if m else "", source])
    added = [(c, n) for c, n in sorted(rows) if c not in ours and c not in known]
    with EXT.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        for code, name in added:
            w.writerow({"security_code": code, "security_name": name, "layer": "steel_other", "segment": "钢铁（东方财富行业板块）",
                        "why": "A 股钢铁企业，42 家以外", "verified": "N"})
    inside = sum(1 for c, _ in rows if c in ours)
    print(f"{len(rows)} steel companies on the board; {inside} already among the 42; {len(added)} added as steel_other")
    print(f"-> {OUT.relative_to(ROOT)}；新增名单已写入 {EXT.relative_to(ROOT)}")
    missing = [m["security_name"] for m in ours.values() if m["tier"] == "core" and m["security_code"] not in {c for c, _ in rows}]
    if missing:
        print("核心钢厂不在该板块（板块口径不同，不影响项目）：", "、".join(missing))


if __name__ == "__main__":
    main()
