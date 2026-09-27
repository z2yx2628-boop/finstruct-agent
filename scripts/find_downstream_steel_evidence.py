"""Step 1 of the cross-layer work: find, in each end user's own latest annual report, the sentences that
say steel is a (main) raw material or cost item, so its link to the steel products can go from C-grade
(industry knowledge) to B-grade (the company's own disclosure). A person confirms each quote.

    python scripts/find_downstream_steel_evidence.py
Downloads to data/raw/annual_reports/<code>_<year>.pdf (Sina mirror) and writes
data/reference/downstream_steel_evidence_candidates.csv (up to 6 candidate sentences per company, with page).
Nothing is written to downstream_users.csv: that happens only after the quotes are confirmed.
"""
import csv
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.find_analysis_corpus import HEADERS, pdf_url  # noqa: E402

LIST = "https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_Bulletin/stockid/{code}/page_type/ndbg.phtml"
ENTRY = re.compile(r"(\d{4}-\d{2}-\d{2})(?:\s|&nbsp;)*<a[^>]*?href=['\"][^'\"]*?id=(\d+)['\"][^>]*>(.*?)</a>", re.S)
RAW = ROOT / "data" / "raw" / "annual_reports"
OUT = ROOT / "data" / "reference" / "downstream_steel_evidence_candidates.csv"
STEEL = re.compile(r"钢材|钢板|板材|钢铁|热轧|冷轧|中厚板|型钢|钢管|钢筋|螺纹钢|特钢|不锈钢")
CONTEXT = re.compile(r"原材料|原料|采购|成本|大宗商品|价格波动|材料费|物资")


def annual_reports(code: str) -> list[tuple[str, str, str]]:
    with urllib.request.urlopen(urllib.request.Request(LIST.format(code=code), headers=HEADERS), timeout=30) as r:
        html = r.read().decode("gbk", errors="replace")
    out = []
    for day, doc_id, title in ENTRY.findall(html):
        title = re.sub(r"<[^>]+>", "", title).strip()
        if re.search(r"年年度报告", title) and not re.search(r"摘要|英文|更正|补充|取消", title):
            out.append((day, doc_id, title))
    return out


def download(code: str) -> tuple[Path, str] | None:
    for day, doc_id, title in annual_reports(code)[:3]:          # latest first; the mirror sometimes 404s
        year = re.search(r"(20\d\d)", title).group(1) if re.search(r"(20\d\d)", title) else day[:4]
        path = RAW / f"{code}_{year}.pdf"
        if path.exists():
            return path, title
        try:
            req = urllib.request.Request(pdf_url(code, day, doc_id), headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if data[:4] == b"%PDF":
                RAW.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                return path, title
        except Exception as error:
            print(f"  {code} {title}: {type(error).__name__}")
        time.sleep(1.5)
    return None


def candidates(pdf: Path, limit: int = 6) -> list[dict]:
    import fitz
    found = []
    with fitz.open(pdf) as doc:
        for number, page in enumerate(doc, 1):
            text = re.sub(r"\s+", "", page.get_text())
            for sentence in re.split(r"(?<=[。；])", text):
                if STEEL.search(sentence) and CONTEXT.search(sentence) and 8 <= len(sentence) <= 220:
                    score = len(STEEL.findall(sentence)) + 2 * len(CONTEXT.findall(sentence)) + \
                        (3 if re.search(r"主要原材料|原材料.{0,10}(包括|主要为|为)", sentence) else 0)
                    found.append({"page": number, "sentence": sentence, "score": score})
    seen, out = set(), []
    for c in sorted(found, key=lambda c: (-c["score"], c["page"])):
        if c["sentence"] not in seen:
            seen.add(c["sentence"])
            out.append(c)
        if len(out) == limit:
            break
    return out


def main() -> None:
    with (ROOT / "data" / "reference" / "downstream_users.csv").open(encoding="utf-8-sig", newline="") as f:
        users = list(csv.DictReader(f))
    rows = []
    for u in users:
        got = download(u["security_code"])
        if not got:
            print(f"[fail] {u['security_code']} {u['security_name']}: 没下载到年报")
            rows.append({"security_code": u["security_code"], "security_name": u["security_name"], "report": "", "rank": "",
                         "page": "", "sentence": "未下载到年报，请手动下载后放到 data/raw/annual_reports/", "confirm": ""})
            continue
        path, title = got
        cands = candidates(path)
        print(f"[ok]   {u['security_code']} {u['security_name']}：{title}，候选 {len(cands)} 句")
        for i, c in enumerate(cands, 1):
            rows.append({"security_code": u["security_code"], "security_name": u["security_name"], "report": title,
                         "rank": i, "page": c["page"], "sentence": c["sentence"], "confirm": ""})
        if not cands:
            rows.append({"security_code": u["security_code"], "security_name": u["security_name"], "report": title,
                         "rank": "", "page": "", "sentence": "年报中没有找到同时提到钢材和原材料/成本的句子", "confirm": ""})
        time.sleep(1.5)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["security_code", "security_name", "report", "rank", "page", "sentence", "confirm"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"\n-> {OUT.relative_to(ROOT)}：请在 confirm 列对能作为证据的句子填 Y（每家至少一句）")


if __name__ == "__main__":
    main()
