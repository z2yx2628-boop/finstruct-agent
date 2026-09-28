"""⑭ Extension companies (coking coal / coke upstream, steel-using downstream leaders): fetch their quarterly
summary and prices, then score each layer AGAINST ITS OWN PEERS with the same fragility method.
They are never mixed into the 24-mill ranking; results go to data/snapshots_extension/<as_of>/.

    python scripts/score_extension.py                  # fetch (network) + score, as of today
    python scripts/score_extension.py --offline        # score from cached data only
    python scripts/score_extension.py --as-of 2025-01-31 --offline

Caveats written into the output: the downstream group mixes industries (autos, machinery, appliances,
construction), so leverage and margins are not strictly comparable; tiers are a rough screen, not a verdict.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.update_all import QDIR, market_metrics, prices, read_rows, refresh_abstract, refresh_prices  # noqa: E402
from src.fragility import VERSION, score  # noqa: E402
from src.market import add_excess_return  # noqa: E402
from src.quarterly import latest_public_period, parse_abstract  # noqa: E402

MANIFEST = ROOT / "data" / "manifests" / "extension_universe.csv"
OUT = ROOT / "data" / "snapshots_extension"
CAVEAT = {"upstream": "焦煤、焦炭企业互为同行，按同一方法评分。",
          "downstream": "下游组跨汽车、机械、家电、建筑等行业，杠杆和毛利率天然不同，只作粗筛，不作结论。"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    with MANIFEST.open(encoding="utf-8-sig", newline="") as f:
        companies = list(csv.DictReader(f))
    failures = []
    if not args.offline:
        for m in companies:
            for label, job in (("quarterly", lambda: refresh_abstract(m["security_code"])),
                               ("prices", lambda: refresh_prices(m["security_code"], args.as_of))):
                try:
                    job()
                except Exception as error:  # noqa: BLE001
                    failures.append(f"{m['security_code']} {m['security_name']} {label}: {type(error).__name__}")
                time.sleep(1.5)
            print("[updated]", m["security_code"], m["security_name"])
    period = latest_public_period(args.as_of)
    out = OUT / args.as_of
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for layer in ("upstream", "downstream"):
        rows = []
        for m in (c for c in companies if c["layer"] == layer):
            path = QDIR / f"{m['security_code']}_abstract.csv"
            periods = parse_abstract(read_rows(path)) if path.exists() else {}
            metrics = dict(periods.get(period) or {"period": period})
            metrics.update(market_metrics(prices(m["security_code"]), args.as_of))
            rows.append({"security_code": m["security_code"], "security_name": m["security_name"], **metrics})
        add_excess_return(rows)
        results = score(rows, [], args.as_of, period)
        for r in results:
            r["peer_group"] = f"extension_{layer}"
        fields = list(dict.fromkeys(k for r in results for k in r))
        with (out / f"fragility_{layer}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(results)
        summary[layer] = {r["security_name"]: r["tier_label"] for r in results}
    (out / "meta.json").write_text(json.dumps({"version": VERSION, "as_of": args.as_of, "period": period, "caveat": CAVEAT,
                                               "failures": failures}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if failures:
        print("FAILED:", *failures, sep="\n  ")


if __name__ == "__main__":
    main()
