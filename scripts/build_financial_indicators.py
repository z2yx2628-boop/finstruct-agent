"""Build data/external/financials/indicators.csv (24 core mills x FY2021-2025).

Run scripts/fetch_financials.py first.
    python scripts/build_financial_indicators.py
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_financials import RAW, core_mills  # noqa: E402
from src.financial_indicators import INDICATORS, INPUTS, build  # noqa: E402

OUT = ROOT / "data" / "external" / "financials" / "indicators.csv"
YEARS = range(2021, 2026)


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fmt(value):
    if isinstance(value, float):
        return f"{value:.6g}"
    return "" if value is None else value


def main() -> None:
    fields = ["security_code", "security_name", "segment", "fiscal_year", "notice_date", *INDICATORS,
              *[f"raw_{k}" for cols in INPUTS.values() for k in cols]]
    rows, missing = [], []
    for m in core_mills():
        code = m["security_code"]
        paths = {s: RAW / f"{code}_{s}.csv" for s in ("balance", "income", "cashflow")}
        if not all(p.exists() for p in paths.values()):
            missing.append(f"{code} {m['security_name']}")
            continue
        built = build(read(paths["balance"]), read(paths["income"]), read(paths["cashflow"]), YEARS)
        years = {r["fiscal_year"] for r in built}
        for y in YEARS:
            if y not in years:
                missing.append(f"{code} {m['security_name']} FY{y}")
        for r in built:
            rows.append({"security_code": code, "security_name": m["security_name"], "segment": m["segment"], **r})
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
