"""List candidate capacity announcements for the V5 holdout set.

Queries CNINFO announcement listings for steel issuers that are NOT used in
any existing development or blind set, keeps titles that look like capacity
events, and writes a CSV for manual selection. Titles only: no PDF is
downloaded or read, so this step cannot leak Gold information.

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\find_capacity_holdout_candidates.py
"""
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "data" / "manifests" / "capacity_holdout_candidates.csv"
DATE_RANGE = "2019-01-01~2026-09-23"

# Issuers already used in capacity_dev, capacity_blind or capacity_v5_dev.
USED_CODES = {
    "600019", "000709", "000932", "600581", "600231", "601686",
    "601003", "000717", "600282", "000708", "600569", "002843", "301217",
}

STEEL_ISSUERS = {
    "000959": "首钢股份", "000825": "太钢不锈", "000898": "鞍钢股份",
    "000761": "本钢板材", "000778": "新兴铸管", "002110": "三钢闽光",
    "002075": "沙钢股份", "600010": "包钢股份", "600022": "山东钢铁",
    "600126": "杭钢股份", "600307": "酒钢宏兴", "600399": "抚顺特钢",
    "600507": "方大特钢", "600782": "新钢股份", "600808": "马钢股份",
    "601005": "重庆钢铁", "600117": "西宁特钢", "002318": "久立特材",
    "002478": "常宝股份", "603878": "武进不锈", "603995": "甬金股份",
    "002443": "金洲管道",
}

INCLUDE = re.compile(
    r"投产|投资建设|拟建设|新建|扩建|建设项目|固定资产投资|基建技改|投资框架|"
    r"产能置换|技术改造|技改|升级改造|改造项目|延期|暂停|暂缓|中止|终止|"
    r"项目进展|项目的进展|搬迁"
)
EXCLUDE = re.compile(
    r"核查意见|法律意见|保荐|独立董事|问询|回复|摘要|英文|更正|取消|"
    r"股东大会|股东会|决议公告|激励|回购|债券|可转|评级|担保|关联交易|"
    r"审计|年度报告|季度报告|半年度报告|会计师|专项报告|存放与|"
    r"使用情况|H股|监事会|说明会|复牌|停牌|交易异常"
)

PATTERNS = [
    ("suspension", r"暂停|暂缓|中止"),
    ("termination", r"终止"),
    ("delay", r"延期"),
    ("framework_plan", r"固定资产投资|基建技改|投资框架|投资计划"),
    ("replacement", r"产能置换"),
    ("commissioning", r"投产"),
    ("technical_upgrade", r"技术改造|技改|升级改造|改造项目"),
    ("progress", r"进展"),
    ("construction", r"投资建设|拟建设|新建|扩建|建设项目|搬迁"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch",
}


def post(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def org_id(code: str) -> str | None:
    result = post(
        "http://www.cninfo.com.cn/new/information/topSearch/query",
        {"keyWord": code, "maxNum": 10},
    )
    for item in result or []:
        if item.get("code") == code:
            return item.get("orgId")
    return None


def announcements(code: str, org: str):
    is_sz = code.startswith(("0", "3"))
    page = 1
    while True:
        result = post(
            "http://www.cninfo.com.cn/new/hisAnnouncement/query",
            {
                "pageNum": page,
                "pageSize": 30,
                "column": "szse" if is_sz else "sse",
                "tabName": "fulltext",
                "plate": "sz" if is_sz else "sh",
                "stock": f"{code},{org}",
                "searchkey": "",
                "secid": "",
                "category": "",
                "trade": "",
                "seDate": DATE_RANGE,
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            },
        )
        items = result.get("announcements") or []
        yield from items
        if not result.get("hasMore") or not items:
            return
        page += 1
        time.sleep(0.3)


def classify(title: str) -> str:
    for name, pattern in PATTERNS:
        if re.search(pattern, title):
            return name
    return "other"


def main() -> int:
    rows = []
    seen = set()
    for code, name in STEEL_ISSUERS.items():
        if code in USED_CODES:
            continue
        try:
            org = org_id(code)
            if not org:
                print(f"[skip] {code} {name}: orgId not found")
                continue
            count = 0
            for item in announcements(code, org):
                title = re.sub(r"<[^>]+>", "", item.get("announcementTitle", ""))
                if not INCLUDE.search(title) or EXCLUDE.search(title):
                    continue
                url = "https://static.cninfo.com.cn/" + item["adjunctUrl"]
                if url in seen or not url.upper().endswith(".PDF"):
                    continue
                seen.add(url)
                date = time.strftime(
                    "%Y-%m-%d",
                    time.localtime(item["announcementTime"] / 1000),
                )
                rows.append({
                    "security_code": code,
                    "security_name": name,
                    "announcement_date": date,
                    "pattern_guess": classify(title),
                    "announcement_title": title,
                    "source_url": url,
                })
                count += 1
            print(f"[ok]   {code} {name}: {count} candidates")
        except Exception as error:  # keep going for other issuers
            print(f"[fail] {code} {name}: {error}")
        time.sleep(0.5)

    rows.sort(key=lambda r: (r["pattern_guess"], r["security_code"],
                             r["announcement_date"]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else
                                ["security_code"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n{len(rows)} candidates written to {OUTPUT}")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
