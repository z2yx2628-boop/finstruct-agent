"""Collect Y1 credit events for the event study (docs/event_study_preregistration.md).

1. All announcement titles of the 24 core mills since 2019-01-01 from the Sina announcement list
   (the same source as find_analysis_corpus.py), cached per company in data/event_study/titles/.
2. Hard events: titles matched by the pre-registered patterns -> data/event_study/event_candidates.csv
   with empty `include` / `review_note` columns for the manual review (saved as events_reviewed.csv).
3. Soft events: annual parent net loss >= 5% of year-end equity, from the cached Sina financial abstract
   -> data/event_study/loss_events.csv (no review needed; dated at the statutory annual deadline).

    python scripts/collect_credit_events.py              # fetch titles (network), then classify
    python scripts/collect_credit_events.py --offline    # classify cached titles only
    python scripts/collect_credit_events.py 000761 600231   # (re)fetch only these companies

No score is read here: events are collected and reviewed before they are joined with any snapshot.
"""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_financials import core_mills  # noqa: E402
from src.quarterly import available_by, parse_abstract  # noqa: E402

OUT = ROOT / "data" / "event_study"
TITLES = OUT / "titles"
QDIR = ROOT / "data" / "external" / "financials" / "quarterly"
SINCE, UNTIL = "2019-01-01", "2026-04-30"
MAX_PAGES = 150
LOSS_SHARE = 0.05

# pre-registered (docs/event_study_preregistration.md, section 4.1); do not edit after the freeze
EXCLUDE = re.compile(r"解除|撤销|解冻|终止|申请撤销|摘帽|完成|结束|补充更正|更正|英文|摘要|说明会|问询|回复|法律意见|核查意见")
PATTERNS = [
    ("guarantee_default", re.compile(r"逾期担保|担保.{0,12}(逾期|代偿)|承担.{0,6}(连带)?(保证|担保)责任")),
    ("debt_default", re.compile(r"(借款|贷款|债务|票据|债券|融资|商票).{0,10}(逾期|违约|未能.{0,4}(兑付|偿还|清偿))"
                                r"|未按期(兑付|偿还)|债务违约")),
    ("freeze", re.compile(r"(股份|股权|资产|账户|银行账户).{0,10}(司法冻结|被冻结|轮候冻结|司法拍卖|司法划转)")),
    ("st", re.compile(r"退市风险警示|其他风险警示|实施.{0,4}风险警示")),
    ("audit", re.compile(r"非标准(无保留)?(审计)?意见|保留意见|无法表示意见|否定意见")),
    ("rating", re.compile(r"评级.{0,8}(下调|调低|下降)|(下调|调低).{0,8}评级|负面观察|展望.{0,4}负面")),
    ("restructuring", re.compile(r"破产重整|预重整|破产清算")),
]
TITLE_FIELDS = ["security_code", "security_name", "notice_date", "doc_id", "title", "source_url"]
CAND_FIELDS = ["security_code", "security_name", "notice_date", "event_type", "title", "source_url", "include", "review_note"]


def classify(title: str) -> str | None:
    if EXCLUDE.search(title):
        return None
    for kind, pattern in PATTERNS:
        if pattern.search(title):
            return kind
    return None


def fetch_titles(code: str, name: str) -> list[dict]:
    from scripts.find_analysis_corpus import fetch_page, pdf_url
    rows, page = [], 1
    while page <= MAX_PAGES:
        items = fetch_page(code, page)
        if not items:
            break
        rows += [{"security_code": code, "security_name": name, "notice_date": i["notice_date"][:10], "doc_id": i["doc_id"],
                  "title": i["title"], "source_url": pdf_url(code, i["notice_date"][:10], i["doc_id"])}
                 for i in items if SINCE <= i["notice_date"][:10]]
        if min(i["notice_date"] for i in items) < SINCE:
            break
        page += 1
        time.sleep(1)
    else:
        print(f"  [{code}] stopped at {MAX_PAGES} pages; earliest title {rows[-1]['notice_date'] if rows else '-'}")
    return rows


def write(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def loss_events(mills: list[dict]) -> list[dict]:
    out = []
    for m in mills:
        path = QDIR / f"{m['security_code']}_abstract.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            periods = parse_abstract(list(csv.reader(f)))
        for period, p in sorted(periods.items()):
            if not period.endswith("1231") or not ("2018" <= period[:4] <= "2025"):
                continue
            profit, equity = p.get("parent_netprofit"), p.get("equity")
            if profit is None or equity is None or equity <= 0 or profit >= 0:
                continue
            share = -profit / equity
            if share >= LOSS_SHARE:
                out.append({"security_code": m["security_code"], "security_name": m["security_name"],
                            "event_date": available_by(period), "event_type": "annual_loss", "period": period,
                            "parent_netprofit_yi": round(profit / 1e8, 2), "equity_yi": round(equity / 1e8, 2),
                            "loss_to_equity": round(share, 4)})
    return out


def main() -> None:
    args = sys.argv[1:]
    offline = "--offline" in args
    codes = {a for a in args if a.isdigit()}
    mills = core_mills()
    failures = []
    if not offline:
        for m in mills:
            code, name = m["security_code"], m["security_name"]
            cache = TITLES / f"{code}.csv"
            if cache.exists() and code not in codes:
                continue
            try:
                rows = fetch_titles(code, name)
                write(cache, TITLE_FIELDS, rows)
                print(f"[{code} {name}] {len(rows)} titles since {SINCE}; earliest {min((r['notice_date'] for r in rows), default='-')}")
            except Exception as error:  # noqa: BLE001 - keep going, report at the end
                failures.append(f"{code} {name}: {type(error).__name__}: {str(error)[:80]}")
            time.sleep(1)

    candidates, coverage = [], []
    for m in mills:
        titles = read(TITLES / f"{m['security_code']}.csv")
        coverage.append((m["security_name"], len(titles), min((t["notice_date"] for t in titles), default="-")))
        for t in titles:
            kind = classify(t["title"]) if t["notice_date"] <= UNTIL else None
            if kind:
                candidates.append({"security_code": t["security_code"], "security_name": t["security_name"],
                                   "notice_date": t["notice_date"], "event_type": kind, "title": t["title"],
                                   "source_url": t["source_url"], "include": "", "review_note": ""})
    candidates.sort(key=lambda r: (r["security_code"], r["notice_date"]))
    write(OUT / "event_candidates.csv", CAND_FIELDS, candidates)
    losses = loss_events(mills)
    write(OUT / "loss_events.csv", ["security_code", "security_name", "event_date", "event_type", "period",
                                    "parent_netprofit_yi", "equity_yi", "loss_to_equity"], losses)

    print("\ntitle coverage (company, titles, earliest):")
    for name, n, first in coverage:
        flag = "  <-- missing or late" if n == 0 or first > "2019-03-31" else ""
        print(f"  {name}: {n}, {first}{flag}")
    by_type = {}
    for c in candidates:
        by_type[c["event_type"]] = by_type.get(c["event_type"], 0) + 1
    print(f"\n{len(candidates)} hard-event candidates -> {(OUT / 'event_candidates.csv').relative_to(ROOT)}  {by_type}")
    print(f"{len(losses)} annual-loss events (>= {LOSS_SHARE:.0%} of equity) -> {(OUT / 'loss_events.csv').relative_to(ROOT)}")
    if failures:
        print("FAILED:", *failures, sep="\n  ")


if __name__ == "__main__":
    main()
