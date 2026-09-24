"""List candidate announcements (titles only) for the direction-3 analysis corpus.

For each of the 24 core mills, pages through the Sina Finance announcement list (CNINFO
and the Eastmoney announcement API are unreachable from the project network), keeps titles that match a direction-1 task and writes
data/manifests/analysis_corpus_candidates.csv. No PDF is downloaded or read.

Documents already used as development / test Gold are marked `used_in`; final-test
documents are marked `final_test` and must never be selected before the freeze.

    python scripts/find_analysis_corpus.py                       # 2024-01-01 .. today
    python scripts/find_analysis_corpus.py --since 2019-01-01 600408 600231   # backtest windows
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_financials import UNIVERSE, core_mills  # noqa: E402

EXTRA = {"600516": "方大炭素"}  # backtest counterparties outside the 42-company universe

OUT = ROOT / "data" / "manifests" / "analysis_corpus_candidates.csv"
LIST = "https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/{code}.phtml?Page={page}"
PDF = ("http://file.finance.sina.com.cn/211.154.219.97:9494/MRGG/{board}/"
       "{y}/{y}-{m}/{day}/{doc_id}.PDF")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36",
           "Referer": "https://vip.stock.finance.sina.com.cn/"}
ENTRY = re.compile(r"(\d{4}-\d{2}-\d{2})(?:\s|&nbsp;)*<a[^>]*?href=['\"][^'\"]*vCB_AllBulletinDetail\.php\?"
                   r"stockid=\d+&(?:amp;)?id=(\d+)['\"][^>]*>(.*?)</a>", re.S)

TASKS = [  # (task, pattern) - first match wins
    ("related_party", re.compile(r"日常关[联连]交易|日常经营相关的关[联连]交易|持续关[联连]交易|关[联连]交易(?:的)?(?:预计|框架|(?:补充)?协议|额度)")),
    ("guarantee", re.compile(r"担保")),
    ("capacity", re.compile(r"产能|投产|技术改造|技改|建设项目|检修|停产|项目.{0,6}(延期|终止|暂停)|高炉|转炉|电炉")),
    ("pledge", re.compile(r"质押")),
]
EXCLUDE = re.compile(r"意见|核查|法律|独立董事|监事会|保荐|英文|摘要|问询|回复|更正|补充更正|取消|说明会|"
                     r"会议资料|决议|通知|制度|章程|激励|H股|海外监管|债券|跟踪评级|评级报告")
FIELDS = ["security_code", "security_name", "notice_date", "task", "title", "doc_id", "source_url", "used_in"]


def norm(title: str) -> str:
    return re.sub(r"[\s（）()“”\"'：:，,、]", "", title or "")


def used_registry() -> tuple[dict, dict]:
    """(code, normalized title) -> split; (code, date) -> split, from every manifest."""
    by_title, by_date = {}, {}
    for path in (ROOT / "data" / "manifests").glob("*.csv"):
        if path.name.startswith("analysis_corpus"):
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                code = (row.get("security_code") or "").zfill(6)
                title = row.get("announcement_title") or row.get("title") or ""
                day = row.get("announcement_date") or row.get("publish_date") or ""
                if code.strip("0") and (title or day):
                    split = path.name.rsplit("_", 1)[0]
                    if title:
                        by_title[(code, norm(title))] = split
                    if day:
                        by_date[(code, day)] = split
    return by_title, by_date


def pdf_url(code: str, day: str, doc_id: str) -> str:
    board = "CNSESH_STOCK" if code.startswith("6") else "CNSESZ_STOCK"
    y, m = day[:4], str(int(day[5:7]))
    return PDF.format(board=board, y=y, m=m, day=day, doc_id=doc_id)


def fetch_page(code: str, page: int) -> list[dict]:
    """-> [{notice_date, doc_id, title}] from one Sina list page (empty when past the last page)."""
    url = LIST.format(code=code, page=page)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
                html = r.read().decode("gbk", errors="replace")
            out = []
            for day, doc_id, title in ENTRY.findall(html):
                title = re.sub(r"<[^>]+>", "", title).strip()
                title = re.sub(r"^[^：:]{2,8}[：:]", "", title)  # drop the "方大特钢：" prefix
                out.append({"notice_date": day, "doc_id": doc_id, "title": title})
            if page == 1 and not out:  # page format changed? keep it for inspection
                debug = ROOT / "data" / "external" / "probe" / f"sina_list_{code}.html"
                debug.parent.mkdir(parents=True, exist_ok=True)
                debug.write_text(html, encoding="utf-8")
                print(f"  no entries parsed on page 1; saved {debug.relative_to(ROOT)}")
            return out
        except Exception as error:
            if attempt == 2:
                raise
            print(f"  retry {code} page {page}: {error}")
            time.sleep(5 * (attempt + 1))
    return []


def classify(title: str) -> str | None:
    if EXCLUDE.search(title):
        return None
    for task, pattern in TASKS:
        if pattern.search(title):
            return task
    return None


def main() -> None:
    args = sys.argv[1:]
    since = "2024-01-01"
    if "--since" in args:
        i = args.index("--since")
        since = args[i + 1]
        del args[i:i + 2]
    codes = set(args)
    by_title, by_date = used_registry()
    rows, failures = [], []
    mills = core_mills()
    if codes:  # explicit codes may be any universe company (e.g. 安泰集团 for a backtest)
        with UNIVERSE.open(encoding="utf-8-sig", newline="") as f:
            mills = [r for r in csv.DictReader(f) if r["security_code"] in codes]
        mills += [{"security_code": c, "security_name": n} for c, n in EXTRA.items() if c in codes]
    for mill in mills:
        code, name = mill["security_code"], mill["security_name"]
        kept, page = 0, 1
        try:
            while True:
                items = fetch_page(code, page)
                if not items:
                    break
                for item in items:
                    day = (item.get("notice_date") or "")[:10]
                    if day < since:
                        continue
                    title = item["title"]
                    task = classify(title)
                    if not task:
                        continue
                    used = by_title.get((code, norm(title))) or by_date.get((code, day)) or ""
                    rows.append({"security_code": code, "security_name": name, "notice_date": day, "task": task,
                                 "title": title, "doc_id": item["doc_id"],
                                 "source_url": pdf_url(code, day, item["doc_id"]), "used_in": used})
                    kept += 1
                if min(i["notice_date"] for i in items) < since or page >= 40:
                    break
                page += 1
                time.sleep(1)
        except Exception as error:
            failures.append(f"{code} {name}: {error}")
        print(f"[{code} {name}] {kept} candidate titles")
        time.sleep(1)
    rows.sort(key=lambda r: (r["security_code"], r["task"], r["notice_date"]))
    out = OUT if not codes else OUT.with_name(f"analysis_corpus_candidates_{'_'.join(sorted(codes))}.csv")
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    by_task = {}
    for r in rows:
        by_task[r["task"]] = by_task.get(r["task"], 0) + 1
    print(f"\n{len(rows)} candidates since {since} -> {out.relative_to(ROOT)}  {by_task}")
    print(f"already used (dev/test/final): {sum(1 for r in rows if r['used_in'])}")
    if failures:
        print("FAILED:", *failures, sep="\n  ")


if __name__ == "__main__":
    main()
