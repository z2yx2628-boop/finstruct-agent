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
if "--output" in sys.argv:
    OUTPUT = PROJECT_ROOT / sys.argv[sys.argv.index("--output") + 1]
DATE_RANGE = "2018-01-01~2026-09-23"

# Issuers already used in capacity_dev, capacity_blind or capacity_v5_dev.
USED_CODES = {
    "600019", "000709", "000932", "600581", "600231", "601686",
    "601003", "000717", "600282", "000708", "600569", "002843", "301217",
}

# Also exclude every issuer that appears in any existing capacity manifest.
for manifest in (PROJECT_ROOT / "data" / "manifests").glob("capacity*sources.csv"):
    with manifest.open(encoding="utf-8-sig") as handle:
        USED_CODES.update(
            row["security_code"].zfill(6)
            for row in csv.DictReader(handle)
            if row.get("security_code")
        )

STEEL_ISSUERS = {
    "000959": "首钢股份", "000825": "太钢不锈", "000898": "鞍钢股份",
    "000761": "本钢板材", "000778": "新兴铸管", "002110": "三钢闽光",
    "002075": "沙钢股份", "600010": "包钢股份", "600022": "山东钢铁",
    "600126": "杭钢股份", "600307": "酒钢宏兴", "600399": "抚顺特钢",
    "600507": "方大特钢", "600782": "新钢股份", "600808": "马钢股份",
    "601005": "重庆钢铁", "600117": "西宁特钢", "002318": "久立特材",
    "002478": "常宝股份", "603878": "武进不锈", "603995": "甬金股份",
    "002443": "金洲管道",
    "000629": "钒钛股份", "002756": "永兴材料", "688186": "广大特材",
    "300881": "盛德鑫泰", "300034": "钢研高纳", "600295": "鄂尔多斯",
    "002541": "鸿路钢构", "600231": "凌钢股份", "000923": "河钢资源",
    "600019": "宝钢股份", "000709": "河钢股份", "000932": "华菱钢铁",
    "600581": "八一钢铁", "601003": "柳钢股份", "000717": "中南股份",
    "600282": "南钢股份", "000708": "中信特钢", "600569": "安阳钢铁",
    "600307": "酒钢宏兴", "600399": "抚顺特钢", "603878": "武进不锈",
    "603995": "甬金股份",
}

INCLUDE = re.compile(
    r"投产|投资建设|拟建设|新建|扩建|建设项目|固定资产投资|基建技改|投资框架|"
    r"产能置换|技术改造|技改|升级改造|改造项目|延期|暂停|暂缓|中止|终止|"
    r"项目进展|项目的进展|搬迁|高炉|转炉|电炉|焦炉|生产线|产线|基地"
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


def post(url: str, data: dict, attempts: int = 4) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, data=body, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=40) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:
            if attempt == attempts - 1:
                raise
            time.sleep(5 * (attempt + 1))


def org_id(code: str) -> str | None:
    result = post(
        "http://www.cninfo.com.cn/new/information/topSearch/query",
        {"keyWord": code, "maxNum": 10},
    )
    for item in result or []:
        if item.get("code") == code:
            return item.get("orgId")
    return None


CAPACITY_KEYWORDS = (
    "项目", "投产", "投资计划", "框架计划", "延期", "终止", "暂停", "暂缓",
    "生产线", "高炉", "技术改造", "产能",
)
GUARANTEE_KEYWORDS = ("担保",)

# --task guarantee switches keywords and title filters to guarantee notices.
TASK = "capacity"
if "--task" in sys.argv:
    TASK = sys.argv[sys.argv.index("--task") + 1]
SEARCH_KEYWORDS = GUARANTEE_KEYWORDS if TASK == "guarantee" else CAPACITY_KEYWORDS


def announcements(code: str, org: str):
    """Ask CNINFO to filter by keyword instead of paging every announcement."""
    is_sz = code.startswith(("0", "3"))
    for keyword in SEARCH_KEYWORDS:
        page = 1
        while page <= 5:
            result = post(
                "http://www.cninfo.com.cn/new/hisAnnouncement/query",
                {
                    "pageNum": page,
                    "pageSize": 30,
                    "column": "szse" if is_sz else "sse",
                    "tabName": "fulltext",
                    "plate": "sz" if is_sz else "sh",
                    "stock": f"{code},{org}",
                    "searchkey": keyword,
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
                break
            page += 1
            time.sleep(0.2)


GUARANTEE_INCLUDE = re.compile(r"担保")
GUARANTEE_EXCLUDE = re.compile(
    r"制度|管理办法|核查意见|法律意见|独立董事|摘要|英文|更正|股东大会|股东会|"
    r"决议公告|审计|年度报告|季度报告|半年度报告|专项说明|质押|债券|可转"
)
GUARANTEE_PATTERNS = [
    ("guarantee_overdue", r"逾期|代偿|诉讼"),
    ("guarantee_release", r"解除|到期|终止"),
    ("guarantee_related", r"关联"),
    ("guarantee_annual_limit", r"额度|预计|年度"),
    ("guarantee_progress", r"进展|实施"),
    ("guarantee_single", r"担保"),
]


def classify(title: str) -> str:
    if TASK == "guarantee":
        for name, pattern in GUARANTEE_PATTERNS:
            if re.search(pattern, title):
                return name
        return "other"
    for name, pattern in PATTERNS:
        if re.search(pattern, title):
            return name
    return "other"


# Final test set (docs/steel_universe.md): never searched for development or
# task test sets. 方大特钢 was already used for guarantee development, so it
# stays in the final set for capacity/maintenance only.
RESERVED_FINAL = {"000898", "600808", "600010", "600507", "600782", "600022", "002075", "000825"}


def guarantee_issuers() -> dict[str, str]:
    """Core steel mills eligible for the guarantee test set."""
    used = set()
    sources = PROJECT_ROOT / "data" / "manifests" / "guarantee_sources.csv"
    if sources.exists():
        with sources.open(encoding="utf-8-sig") as handle:
            used = {row["security_code"].zfill(6) for row in csv.DictReader(handle)}
    with (PROJECT_ROOT / "data" / "manifests" / "steel_universe.csv").open(encoding="utf-8-sig") as handle:
        return {
            row["security_code"]: row["security_name"]
            for row in csv.DictReader(handle)
            if row["tier"] == "core" and row["core_analysis_target"] == "Y"
            and row["security_code"] not in RESERVED_FINAL | used
        }


def main() -> int:
    rows = []
    seen = set()
    issuers = guarantee_issuers() if TASK == "guarantee" else STEEL_ISSUERS
    for code, name in issuers.items():
        if TASK != "guarantee" and code in USED_CODES:
            continue
        try:
            org = org_id(code)
            if not org:
                print(f"[skip] {code} {name}: orgId not found")
                continue
            count = 0
            for item in announcements(code, org):
                title = re.sub(r"<[^>]+>", "", item.get("announcementTitle", ""))
                include, exclude = (
                    (GUARANTEE_INCLUDE, GUARANTEE_EXCLUDE)
                    if TASK == "guarantee" else (INCLUDE, EXCLUDE)
                )
                if not include.search(title) or exclude.search(title):
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
            print(f"[ok]   {code} {name}: {count} candidates", flush=True)
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
