"""Build the template, validate filled rows, and derive overseas/EU shares.

  python scripts/overseas_revenue.py init      # create template (won't overwrite)
  python scripts/overseas_revenue.py check     # validate only
  python scripts/overseas_revenue.py derive    # validate, then fill share columns
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.overseas_revenue import FIELDS, process  # noqa: E402

TARGET = ROOT / "data" / "external" / "overseas_revenue.csv"
UNIVERSE = ROOT / "data" / "manifests" / "steel_universe.csv"
YEARS = range(2019, 2026)  # covers EU safeguard era, CBAM transition (2023-10) up to FY2025


def init() -> None:
    if TARGET.exists():
        sys.exit(f"{TARGET} already exists; refusing to overwrite")
    with UNIVERSE.open(encoding="utf-8-sig", newline="") as f:
        mills = [r for r in csv.DictReader(f)
                 if r["tier"] == "core" and r["core_analysis_target"] == "Y"]
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with TARGET.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for m in mills:
            for year in YEARS:
                writer.writerow({"security_code": m["security_code"],
                                 "security_name": m["security_name"],
                                 "fiscal_year": year, "currency": "CNY"})
    print(f"wrote {len(mills)} mills x {len(YEARS)} years to {TARGET}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "init":
        return init()
    problems = process(TARGET, write=(cmd == "derive"))
    for line, items in problems.items():
        for p in items:
            print(f"line {line}: {p}")
    if problems:
        sys.exit(1)
    print("ok" + (" - shares derived" if cmd == "derive" else ""))


if __name__ == "__main__":
    main()
