"""Completeness check (post hoc): does our announcement list (Sina) contain every announcement that
CNINFO (巨潮资讯网, the exchanges' designated disclosure site) lists for the same company and dates?

    python scripts/check_coverage.py                 # all companies in data/live/announcement_titles
    python scripts/check_coverage.py --end 2026-09-30

For each company the window is (first date in our cached list, --end]: the cache holds the newest
pages of each company's list, so its first day is cut part-way through and is not counted (the first
run, 2026-10-14, counted it; every title it missed fell on that first day). A CNINFO title counts as found
when the same normalised title appears in our list within +-3 days. Titles about guarantees or
related-party transactions -- the documents that build the graph -- are reported separately.
Output: docs/coverage_check.md and data/eval/coverage_check.csv.
"""
import argparse
import csv
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TITLES = ROOT / "data" / "live" / "announcement_titles"
KEY = re.compile(r"担保|关联交易")
PUNCT = re.compile(r"[\s　:：,，。.、()（）《》<>“”\"'‘’\-—_【】\[\]]")


FULLNAME = re.compile(r"^[\u4e00-\u9fff]{2,24}?(?:股份)?有限公司")


def norm(title: str, name: str) -> str:
    t = PUNCT.sub("", str(title or ""))
    t = FULLNAME.sub("", t)
    for n in {name, name.replace("*", ""), name.replace("ST", "")}:
        if n and t.startswith(PUNCT.sub("", n)):
            t = t[len(PUNCT.sub("", n)):]
    return t.replace("股份有限公司", "").replace("有限公司", "")


def cninfo(code: str, start: str, end: str):
    import akshare as ak
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_disclosure_report_cninfo(symbol=code, market="沪深京", keyword="", category="",
                                                        start_date=start.replace("-", ""), end_date=end.replace("-", ""))
            return [(str(r["公告标题"]), str(r["公告时间"])[:10]) for _, r in df.iterrows()]
        except Exception as e:  # network hiccup
            err = e
            time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"{code}: {err}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default="2026-09-30")
    args = ap.parse_args()
    rows, fails = [], []
    for f in sorted(TITLES.glob("*.csv")):
        with f.open(encoding="utf-8-sig", newline="") as fh:
            ours = list(csv.DictReader(fh))
        if not ours:
            continue
        code, name = f.stem, ours[0]["security_name"]
        first = min(r["notice_date"] for r in ours)
        start = (date.fromisoformat(first) + timedelta(days=1)).isoformat()   # first day is cut part-way
        if start > args.end:
            continue
        idx = {}
        for r in ours:
            idx.setdefault(norm(r["title"], name), []).append(date.fromisoformat(r["notice_date"]))
        try:
            theirs = cninfo(code, start, args.end)
        except RuntimeError as e:
            fails.append(str(e))
            print("FAILED", e)
            continue
        theirs = [(t, d) for t, d in theirs if d >= start]
        miss, miss_key, n_key = [], [], 0
        for title, day in theirs:
            k = norm(title, name)
            d = date.fromisoformat(day)
            if day < start:
                continue
            found = any(abs((x - d).days) <= 3 for x in idx.get(k, []))
            if not found:   # tolerate small wording differences
                found = any(abs((x - d).days) <= 3 and (k in t or t in k) and min(len(k), len(t)) >= 8
                            for t, xs in idx.items() for x in xs)
            key = bool(KEY.search(title))
            n_key += key
            if not found:
                miss.append(f"{day} {title}")
                if key:
                    miss_key.append(f"{day} {title}")
        rows.append({"security_code": code, "security_name": name, "start": start, "end": args.end,
                     "cninfo": len(theirs), "found": len(theirs) - len(miss),
                     "cninfo_key": n_key, "found_key": n_key - len(miss_key),
                     "missing_key": " | ".join(miss_key), "missing_sample": " | ".join(miss[:5])})
        print(code, name, f"{len(theirs) - len(miss)}/{len(theirs)}", f"key {n_key - len(miss_key)}/{n_key}")
        time.sleep(1)
    out = ROOT / "data" / "eval" / "coverage_check.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    tot, fnd = sum(r["cninfo"] for r in rows), sum(r["found"] for r in rows)
    tk, fk = sum(r["cninfo_key"] for r in rows), sum(r["found_key"] for r in rows)
    lines = [
        "# 公告抓取完整性核对（事后核对）", "",
        f"运行日期 {date.today().isoformat()}；脚本 `scripts/check_coverage.py`；明细 `data/eval/coverage_check.csv`。", "",
        "对照来源：巨潮资讯网（证监会指定的信息披露网站），经 akshare `stock_zh_a_disclosure_report_cninfo` 获取。",
        "每家公司的核对区间为本系统公告列表中最早一条日期的次日至 " + args.end + "（本系统缓存的是各公司公告列表的最新若干页，最早那一天只保存了一部分，不计入；首次运行（2026-10-14）计入了这一天，当时未找到的标题全部落在这一天）。",
        "同一标题（去掉标点、公司简称和公司全称）在 ±3 天内出现即算找到。", "",
        f"- 公司数：{len(rows)}" + (f"（另有 {len(fails)} 家查询失败）" if fails else ""),
        f"- 全部公告：巨潮 {tot} 份，本系统找到 {fnd} 份，覆盖率 **{fnd / tot:.1%}**" if tot else "- 全部公告：0",
        f"- 标题含“担保”或“关联交易”的公告（建图来源）：巨潮 {tk} 份，找到 {fk} 份，覆盖率 **{fk / tk:.1%}**" if tk else "- 担保 / 关联交易公告：0",
        "", "## 未找到的担保 / 关联交易公告", ""]
    lines += [f"- {r['security_name']}（{r['security_code']}）：{r['missing_key']}" for r in rows if r["missing_key"]] or ["无。"]
    lines += ["", "## 各公司", "", "| 代码 | 简称 | 区间起点 | 巨潮 | 找到 | 担保/关联交易 巨潮 | 找到 |", "| --- | --- | --- | ---: | ---: | ---: | ---: |"]
    lines += [f"| {r['security_code']} | {r['security_name']} | {r['start']} | {r['cninfo']} | {r['found']} | {r['cninfo_key']} | {r['found_key']} |" for r in rows]
    if fails:
        lines += ["", "查询失败：", *[f"- {x}" for x in fails]]
    (ROOT / "docs" / "coverage_check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nall {fnd}/{tot}; key {fk}/{tk}; written docs/coverage_check.md")


if __name__ == "__main__":
    main()
