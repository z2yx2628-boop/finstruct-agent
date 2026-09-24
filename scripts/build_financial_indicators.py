"""Build data/external/financials/indicators.csv for every company whose statements are downloaded.

Years run from FY2021 to the latest annual report found in the data, so a newly published
annual report appears after `fetch_financials.py --refresh` without code changes.
`peer_group` = core for the 24 core mills (the peer set for ranking), other otherwise.
    python scripts/build_financial_indicators.py
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_financials import RAW, universe  # noqa: E402
from src.financial_indicators import INDICATORS, INPUTS, annual_rows, build  # noqa: E402

OUT = ROOT / "data" / "external" / "financials" / "indicators.csv"
FIRST_YEAR = 2021


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fmt(value):
    if isinstance(value, float):
        return f"{value:.6g}"
    return "" if value is None else value


def main() -> None:
    fields = ["security_code", "security_name", "segment", "peer_group", "fiscal_year", "notice_date", *INDICATORS,
              *[f"raw_{k}" for cols in INPUTS.values() for k in cols]]
    rows, missing = [], []
    known = {r["security_code"]: r for r in universe()}
    codes = sorted({p.name.split("_")[0] for p in RAW.glob("*_balance.csv")})
    for code in codes:
        m = known.get(code, {"security_code": code, "security_name": code, "segment": "", "tier": "", "core_analysis_target": ""})
        peer = "core" if m.get("tier") == "core" and m.get("core_analysis_target") == "Y" else "other"
        paths = {s: RAW / f"{code}_{s}.csv" for s in ("balance", "income", "cashflow")}
        if not all(p.exists() for p in paths.values()):
            missing.append(f"{code} {m['security_name']}")
            continue
        balance = read(paths["balance"])
        latest = max(annual_rows(balance), default=FIRST_YEAR)
        years_wanted = range(FIRST_YEAR, latest + 1)
        built = build(balance, read(paths["income"]), read(paths["cashflow"]), years_wanted)
        years = {r["fiscal_year"] for r in built}
        for y in years_wanted:
            if y not in years:
                missing.append(f"{code} {m['security_name']} FY{y}")
        for r in built:
            rows.append({"security_code": code, "security_name": m["security_name"], "segment": m.get("segment", ""),
                         "peer_group": peer, **r})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: fmt(v) for k, v in r.items()} for r in rows)
    print(f"{len(rows)} mill-years written to {OUT.relative_to(ROOT)}")
    if missing:
        print("missing:", "; ".join(missing))


if __name__ == "__main__":
    main()
