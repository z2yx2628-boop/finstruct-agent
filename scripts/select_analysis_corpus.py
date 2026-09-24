"""Pick the analysis corpus from analysis_corpus_candidates.csv with fixed, written rules.

Rules (titles only; nothing is opened):
  related_party : the annual estimate announcements for FY2025 and FY2026 (published from
                  2024-10-01); adjustments, additions, framework/finance agreements and
                  execution-only reports are left out.
  guarantee     : annual guarantee quota announcements from 2024-10-01, every guarantee
                  involving a related or associated party, and for issuers without an annual
                  quota announcement the latest 3 individual guarantee announcements.
  capacity      : every capacity / maintenance announcement.
  pledge        : controlling-shareholder pledge announcements from 2025-01-01 (not pure releases).
Documents used in any dev/test/final set are never selected.

    python scripts/select_analysis_corpus.py
Writes data/manifests/analysis_selection.csv for
    python scripts/download_capacity_holdout.py --split analysis
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "manifests" / "analysis_corpus_candidates.csv"
OUT = ROOT / "data" / "manifests" / "analysis_selection.csv"
FIELDS = ["holdout_id", "security_code", "security_name", "announcement_date", "target_pattern",
          "announcement_title", "source_url", "notes"]

REL_SKIP = re.compile(r"调整|调减|新增|增加|补充|变更|框架|金融服务|租赁|续签|实施主体")
REL_KEEP = re.compile(r"预计|预测|日常关联交易公告|日常关联交易的公告|持续关联交易公告")
G_SKIP = re.compile(r"管理办法|管理规定|融资融券|担保品")
G_QUOTA = re.compile(r"额度|年度")
G_RELATED = re.compile(r"关联|参股|关联方")
P_KEEP = re.compile(r"股份质押(?:的)?公告|部分股份质押|再质押|及质押|补充质押|质押展期|质押延期")
P_RELEASE_ONLY = re.compile(r"解除质押的公告$|全部解除质押|质押解除|过户登记")


def pick(rows: list[dict]) -> list[tuple[dict, str, str]]:
    chosen = []
    by_issuer = defaultdict(list)
    for r in rows:
        if r["used_in"]:
            continue
        t, title, day = r["task"], r["title"], r["notice_date"]
        if t == "related_party":
            if day >= "2024-10-01" and REL_KEEP.search(title) and not REL_SKIP.search(title):
                chosen.append((r, "related_estimate", "annual estimate FY2025/FY2026"))
        elif t == "guarantee":
            if G_SKIP.search(title):
                continue
            if G_RELATED.search(title):
                chosen.append((r, "guarantee_related", "guarantee involving a related/associated party"))
            elif G_QUOTA.search(title) and day >= "2024-10-01":
                chosen.append((r, "guarantee_quota", "annual guarantee quota"))
            else:
                by_issuer[r["security_code"]].append(r)
        elif t == "capacity":
            chosen.append((r, "capacity", "capacity / maintenance"))
        elif t == "pledge":
            if day >= "2025-01-01" and P_KEEP.search(title) and not (P_RELEASE_ONLY.search(title)
                                                                     and not re.search(r"再质押|及质押", title)):
                chosen.append((r, "pledge", "controlling-shareholder pledge"))
    quota_issuers = {r["security_code"] for r, p, _ in chosen if p == "guarantee_quota"}
    for code, items in by_issuer.items():
        if code in quota_issuers:
            continue
        for r in sorted(items, key=lambda x: x["notice_date"])[-3:]:
            chosen.append((r, "guarantee_individual", "latest individual guarantees (no annual quota found)"))
    return chosen


def main() -> None:
    with SRC.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    chosen = sorted(pick(rows), key=lambda x: (x[0]["security_code"], x[1], x[0]["notice_date"]))
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for i, (r, pattern, note) in enumerate(chosen, 1):
            w.writerow({"holdout_id": f"analysis_{i:03d}", "security_code": r["security_code"],
                        "security_name": r["security_name"], "announcement_date": r["notice_date"],
                        "target_pattern": pattern, "announcement_title": r["title"],
                        "source_url": r["source_url"], "notes": f"{note}; sina doc {r['doc_id']}"})
    counts = defaultdict(int)
    for _, p, _ in chosen:
        counts[p] += 1
    print(f"{len(chosen)} documents selected -> {OUT.relative_to(ROOT)}  {dict(counts)}")
    print(f"issuers covered: {len({r['security_code'] for r, _, _ in chosen})}")


if __name__ == "__main__":
    main()
