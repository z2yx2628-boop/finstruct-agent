"""Download the three Eastmoney statements for the 24 core steel mills.

Raw tables go to data/external/financials/raw/<code>_<statement>.csv (git-ignored,
re-downloadable); every file's SHA-256 and row count is logged in
data/external/financials/fetch_log.csv so the indicator table can be traced.
Resumable: files that already exist are skipped.

    python scripts/fetch_financials.py                    # all 24 core mills
    python scripts/fetch_financials.py 600019 600408      # any listed codes (added on demand)
    python scripts/fetch_financials.py --all              # all 42 companies in steel_universe.csv
    python scripts/fetch_financials.py --refresh          # re-download to pick up newly published reports
"""
from __future__ import annotations

import csv
import hashlib
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "data" / "manifests" / "steel_universe.csv"
RAW = ROOT / "data" / "external" / "financials" / "raw"
LOG = ROOT / "data" / "external" / "financials" / "fetch_log.csv"
LOG_FIELDS = ["security_code", "security_name", "statement", "file", "rows", "latest_report", "sha256", "fetched_at"]


def core_mills() -> list[dict]:
    with UNIVERSE.open(encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if r["tier"] == "core" and r["core_analysis_target"] == "Y"]


def em_symbol(code: str) -> str:
    return ("SH" if code.startswith("6") else "SZ") + code


def fetchers():
    """Annual-only endpoints (about 4x fewer requests); fall back to the full report list."""
    import akshare as ak

    def pick(yearly: str, by_report: str):
        fast, slow = getattr(ak, yearly, None), getattr(ak, by_report)
        if fast is None:
            return slow

        def fetch(symbol: str):
            try:
                return fast(symbol=symbol)
            except Exception:
                return slow(symbol=symbol)
        return fetch

    return {
        "balance": pick("stock_balance_sheet_by_yearly_em", "stock_balance_sheet_by_report_em"),
        "income": pick("stock_profit_sheet_by_yearly_em", "stock_profit_sheet_by_report_em"),
        "cashflow": pick("stock_cash_flow_sheet_by_yearly_em", "stock_cash_flow_sheet_by_report_em"),
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def universe() -> list[dict]:
    with UNIVERSE.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def select(codes: list[str], everything: bool) -> list[dict]:
    rows = universe()
    if everything:
        return rows
    if not codes:
        return [r for r in rows if r["tier"] == "core" and r["core_analysis_target"] == "Y"]
    known = {r["security_code"]: r for r in rows}
    return [known.get(c, {"security_code": c, "security_name": c}) for c in codes]


def main(codes: list[str], everything: bool = False, refresh: bool = False) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    mills = select(codes, everything)
    funcs = fetchers()
    log = {}
    if LOG.exists():
        with LOG.open(encoding="utf-8", newline="") as f:
            log = {(r["security_code"], r["statement"]): r for r in csv.DictReader(f)}
    failures = []
    for m in mills:
        code, name = m["security_code"], m["security_name"]
        for statement, fetch in funcs.items():
            path = RAW / f"{code}_{statement}.csv"
            if refresh or not path.exists():
                for attempt in range(3):
                    try:
                        frame = fetch(symbol=em_symbol(code))
                        frame.to_csv(path, index=False, encoding="utf-8-sig")
                        break
                    except Exception as error:  # network hiccups: retry, then record
                        if attempt == 2:
                            failures.append(f"{code} {name} {statement}: {type(error).__name__}: {str(error)[:100]}")
                        time.sleep(3 * (attempt + 1))
                time.sleep(1)
            if not path.exists():
                continue
            with path.open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            latest = max((r["REPORT_DATE"][:10] for r in rows), default="")
            log[(code, statement)] = {
                "security_code": code, "security_name": name, "statement": statement,
                "file": path.relative_to(ROOT).as_posix(), "rows": len(rows), "latest_report": latest,
                "sha256": sha256(path),
                "fetched_at": (None if refresh else log.get((code, statement), {}).get("fetched_at"))
                or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            print(f"[ok] {code} {name} {statement}: {len(rows)} reports, latest {latest}")
    with LOG.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(log.values(), key=lambda r: (r["security_code"], r["statement"])))
    print(f"\n{len(log)} statement files logged in {LOG.relative_to(ROOT)}")
    if failures:
        print("FAILED (rerun the same command to retry only these):")
        print("\n".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    flags = {"--all", "--refresh"}
    main([a for a in sys.argv[1:] if a not in flags], "--all" in sys.argv, "--refresh" in sys.argv)
