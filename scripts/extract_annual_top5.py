"""Top-5 customers and suppliers from annual reports (年报“主要销售客户和主要供应商情况”).

Every A-share annual report states, in the MD&A, the top-5 customers' sales and the top-5 suppliers'
purchases, their share of the year's total sales / purchases, and the related-party part. Shenzhen reports
(and some Shanghai ones) add a table with one line per customer / supplier - often anonymised (客户一, 第一名),
sometimes named.

Reads  data/raw/annual_reports/<code>_<fy>.pdf   (scripts/download_annual_reports.py)
Writes data/reference/annual_concentration.csv   one row per company x year x side:
           top-5 amount and share, related-party amount and share, the implied annual total
           (top-5 amount / its share = 年度销售总额 or 年度采购总额), the largest single share
       data/reference/annual_top5.csv            one row per listed customer / supplier, in the
           supply_relations.csv layout (scripts/build_supply_relations.py merges it)

Nothing is guessed: a figure that is not found stays empty and the row says why (check column).
Amounts go through src/amounts.py (元 / 千元 / 万元 / 亿元 -> 万元).

    python scripts/extract_annual_top5.py
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.amounts import to_wan  # noqa: E402

RAW = ROOT / "data" / "raw" / "annual_reports"
UNIVERSE = ROOT / "data" / "manifests" / "steel_universe.csv"
SOURCES = ROOT / "data" / "manifests" / "annual_report_sources.csv"
CONC = ROOT / "data" / "reference" / "annual_concentration.csv"
TOP5 = ROOT / "data" / "reference" / "annual_top5.csv"
UNIT = r"(?:人民币)?(百万元|千元|万元|亿元|元)"
NUM = r"([\d,]+(?:\.\d+)?)"
SIDES = {
    "customer": {"word": "客户", "act": "销售", "total": "销售", "direction": "downstream", "relation": "前五名客户",
                 "amount_type": "销售额"},
    "supplier": {"word": "供应商", "act": "采购", "total": "采购", "direction": "upstream", "relation": "前五名供应商",
                 "amount_type": "采购额"},
}
ANON = re.compile(r"^(?:第[一二三四五12345]名|(?:客户|供应商|单位|公司)\s*[A-Za-z一二三四五1-5]|[A-Za-z一二三四五]|"
                  r"[A-Za-z]\s*(?:客户|供应商|公司)|(?:客户|供应商)[一二三四五]名?)$")
CONC_FIELDS = ["company_id", "company_name", "fy", "side", "top5_wan", "top5_share", "related_wan", "related_share",
               "total_wan", "largest_share", "rows_found", "rows_named", "page", "check", "source"]
TOP5_FIELDS = ["company_id", "company_name", "direction", "relation", "counterparty", "counterparty_code", "related_party", "year",
               "period", "amount_type", "amount_wan", "share", "share_basis", "share_method", "goods", "source_type", "source",
               "grade", "available_from", "counterparty_named"]


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def pages(path: Path) -> list[str]:
    out = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout
    return out.split("\f")


def num(token: str) -> float:
    return float(token.replace(",", ""))


def section(texts: list[str]) -> tuple[list[tuple[int, str]], int] | None:
    """(page, line) pairs around the first top-5 statement in the MD&A, and the page it starts on."""
    lines = [(i + 1, line) for i, t in enumerate(texts) for line in t.splitlines()]
    for k, (page, line) in enumerate(lines):
        flat = re.sub(r"\s+", "", line)
        if re.search(r"前(五|5)名客户(合计)?销售", flat):
            return lines[max(0, k - 5):k + 110], page
    return None


def totals(flat: str, side: str) -> dict:
    """Top-5 amount / share and the related-party part, in either the Shenzhen or the Shanghai wording."""
    s = SIDES[side]
    w, act, tot = s["word"], s["act"], s["total"]
    out = {}
    m = re.search(rf"前(?:五|5)名{w}合计{act}金额[（(]{UNIT}[）)]{NUM}", flat)          # Shenzhen
    if m:
        out["top5_wan"] = to_wan(num(m.group(2)), m.group(1))
        m2 = re.search(rf"前(?:五|5)名{w}合计{act}金额占年度{tot}总额比例{NUM}%", flat)
        out["top5_share"] = num(m2.group(1)) / 100 if m2 else None
        m3 = re.search(rf"关联方{act}额占年度{tot}总额比例{NUM}%", flat)
        out["related_share"] = num(m3.group(1)) / 100 if m3 else None
        if out.get("related_share") is not None and out.get("top5_share") and out.get("top5_wan") is not None:
            out["related_wan"] = out["top5_wan"] * out["related_share"] / out["top5_share"]
        return out
    m = re.search(rf"前(?:五|5)名{w}(?:的)?{act}(?:收入)?(?:金)?额(?:人民币)?{NUM}{UNIT}[，,]占(?:年度|全年度)(?:全部)?(?:{tot}(?:收入)?总额|营业收入){NUM}%", flat)
    if m:                                                                                  # Shanghai
        out["top5_wan"] = to_wan(num(m.group(1)), m.group(2))
        out["top5_share"] = num(m.group(3)) / 100
        m3 = re.search(rf"关联方{act}(?:收入)?(?:金)?额(?:人民币)?{NUM}{UNIT}[，,]占(?:年度|全年度)(?:全部)?(?:{tot}(?:收入)?总额|营业收入){NUM}%?", flat)
        if m3:
            out["related_wan"] = to_wan(num(m3.group(1)), m3.group(2))
            out["related_share"] = num(m3.group(3)) / 100
    return out


def totals_by_line(lines: list[str], side: str) -> dict:
    """Fallback for reports that print the totals as a small two-year table: label and numbers on one line,
    the share label split over two lines, the unit in a '金额单位：人民币百万元' line. The first number is this year."""
    s = SIDES[side]
    w, act = s["word"], s["act"]
    numbers = lambda t: re.findall(r"(?<![\d.])\d[\d,]*(?:\.\d+)?", t)  # noqa: E731  (space-separated columns)
    out = {}
    for k, line in enumerate(lines):
        flat = re.sub(r"\s+", "", line)
        if not re.search(rf"前(?:五|5)名{w}合计{act}金额(?!占)", flat):
            continue
        after = re.split(r"金额", line, maxsplit=1)[-1] if "金额" in line else line
        found = numbers(re.sub(r"[（(][^）)]*[）)]", "", after))
        if not found:
            continue
        unit = next((m.group(1) for x in lines[max(0, k - 6):k + 1][::-1]
                     for m in [re.search(rf"(?:金额)?单位[:：]{UNIT}", re.sub(r"\s+", "", x))] if m), None)
        if not unit:
            return {}
        out["top5_wan"] = to_wan(num(found[0]), unit)
        for key, label in (("top5_share", rf"前(?:五|5)名{w}合计{act}金额占"), ("related_share", r"关联方")):
            j = next((j for j in range(k + 1, min(k + 10, len(lines))) if re.search(label, re.sub(r"\s+", "", lines[j]))), None)
            if j is None:
                continue
            for x in lines[j:j + 3]:
                got = numbers(re.sub(r"[（(][^）)]*[）)]", "", x))
                if got:
                    out[key] = num(got[0]) / 100
                    break
        if out.get("related_share") is not None and out.get("top5_share"):
            out["related_wan"] = out["top5_wan"] * out["related_share"] / out["top5_share"]
        return out
    return out


def table_unit(block: list[str]) -> str | None:
    text = re.sub(r"\s+", "", " ".join(block))
    m = re.search(rf"(?:销售|采购)(?:金)?额[（(]{UNIT}[）)]", text) or re.search(rf"单位[:：]{UNIT}", text)
    return m.group(1) if m else None


WRAPPED = re.compile(r"^\s*([1-5])\s{2,}([\d,]+(?:\.\d+)?)\s+([\d.]+)\s*%?\s*$")
ROW = re.compile(r"^\s*(?:([1-5])\s+)?(\S(?:.*?\S)?)\s{2,}([\d,]+(?:\.\d+)?)\s+([\d.]+)\s*%?(?:\s+.*)?$")


def rows_of(block: list[str]) -> list[dict]:
    """Table lines: [rank] name  amount  share[%] [note]; the 合计 line is returned separately as name 合计."""
    out = []
    for line in block:
        m = ROW.match(line)
        if not m:
            continue
        name = re.sub(r"\s+", "", m.group(2))
        if name.startswith("合计"):
            out.append({"name": "合计", "amount": num(m.group(3)), "share": float(m.group(4))})
            continue
        if (re.fullmatch(r"[\d,.%\s]+", name) or len(name) > 40 or "年度报告" in name or re.search(r"\d,\d", name)
                or float(m.group(4)) > 100):
            continue
        out.append({"name": name, "amount": num(m.group(3)), "share": float(m.group(4)), "rank": m.group(1) or ""})
    return out


def split_blocks(window: list[tuple[int, str]]) -> dict[str, list[tuple[int, str]]]:
    """The customer part (from the first top-5 statement) and the supplier part (from 主要供应商 / 前五名供应商)."""
    def supplier_start(line: str) -> bool:
        flat = re.sub(r"\s+", "", line)
        return bool((re.search(r"主要供应商情况", flat) and "客户" not in flat)
                    or re.search(r"前(五|5)名供应商(合计)?(的)?采购|来自前五名供应商", flat))
    cut = next((k for k, (_, line) in enumerate(window) if k > 3 and supplier_start(line)), len(window))
    end = next((k for k, (_, line) in enumerate(window) if k > cut + 3
                and re.search(r"^\s*(3、|三、|（?[三3]）?\s*费用|费用$|B\.|报告期内向单个)", line)), len(window))
    return {"customer": window[:cut], "supplier": window[cut:end]}


def tables(window: list[tuple[int, str]]) -> dict[str, tuple[list[dict], str | None, int]]:
    """side -> (rows, unit, page) for each table whose header names 客户名称 / 供应商名称 (wherever it sits:
    some reports put the customer table after the supplier sentence)."""
    lines = [line for _, line in window]
    out = {}
    for k, line in enumerate(lines):
        flat = re.sub(r"\s+", "", line)
        side = "customer" if "客户名称" in flat else "supplier" if ("供应商名称" in flat or "供货商名称" in flat) else None
        if not side or side in out:
            continue
        unit = table_unit(lines[max(0, k - 4):k + 3])
        rows = []
        block = lines[k + 1:k + 30]
        for i, body in enumerate(block):
            flat_body = re.sub(r"\s+", "", body)
            wrapped = WRAPPED.match(body)
            if wrapped:                      # a long name wrapped above and below its number line
                before = block[i - 1].strip() if i > 0 and not ROW.match(block[i - 1]) else ""
                after = block[i + 1].strip() if i + 1 < len(block) and not ROW.match(block[i + 1]) \
                    and not WRAPPED.match(block[i + 1]) else ""
                name = re.sub(r"\s+", "", before + after)
                if name and not re.search(r"名称|合计", name):
                    rows.append({"name": name, "amount": num(wrapped.group(2)), "share": float(wrapped.group(3)),
                                 "rank": wrapped.group(1)})
                    if len(rows) == 5:
                        break
                continue
            same = "客户名称" if side == "customer" else "供应商名称"
            if same in flat_body or ("供货商名称" in flat_body and side == "supplier"):
                continue                     # the header repeated after a page break
            if re.search(r"客户名称|供应商名称|供货商名称|报告期内|其他说明|费用|^注[:：]|^3、|^三、", flat_body):
                break
            got = rows_of([body])
            if got and got[0]["name"] == "合计":
                break
            rows += got
            if len(rows) == 5:
                break
        out[side] = (rows, unit, window[k][0])
    return out


def extract(path: Path, code: str, name: str, fy: str, notice: str) -> tuple[list[dict], list[dict]]:
    texts = pages(path)
    found = section(texts)
    src = f"{fy}年年度报告"
    if not found:
        return ([{"company_id": code, "company_name": name, "fy": fy, "side": s, "check": "section_not_found", "source": src}
                 for s in SIDES], [])
    window, _ = found
    blocks = split_blocks(window)
    found_tables = tables(window)
    conc, relations = [], []
    for side, block in blocks.items():
        s = SIDES[side]
        flat = re.sub(r"\s+", "", "".join(line for _, line in block))
        t = totals(flat, side) or totals_by_line([line for _, line in block], side)
        body, unit, table_page = found_tables.get(side, ([], None, ""))
        page = block[0][0] if block else table_page
        if not unit:
            body = []
        checks = []
        if not t.get("top5_wan"):
            checks.append("top5_not_found")
        if body and t.get("top5_wan"):
            listed = sum(to_wan(r["amount"], unit) or 0 for r in body)
            if listed > 1.01 * t["top5_wan"]:
                checks.append("rows_do_not_add_up")
            elif listed < 0.99 * t["top5_wan"]:
                checks.append("partial_table")       # e.g. only the new customers among the top 5 are listed
        total = t["top5_wan"] / t["top5_share"] if t.get("top5_wan") and t.get("top5_share") else None
        named = [r for r in body if not ANON.match(r["name"])]
        ok_rows = "rows_do_not_add_up" not in checks
        conc.append({"company_id": code, "company_name": name, "fy": fy, "side": side,
                     "top5_wan": round(t["top5_wan"], 2) if t.get("top5_wan") is not None else "",
                     "top5_share": round(t["top5_share"], 4) if t.get("top5_share") is not None else "",
                     "related_wan": round(t["related_wan"], 2) if t.get("related_wan") is not None else "",
                     "related_share": round(t["related_share"], 4) if t.get("related_share") is not None else "",
                     "total_wan": round(total, 2) if total else "",
                     "largest_share": round(max(r["share"] for r in body) / 100, 4) if body and ok_rows and "partial_table" not in checks else "",
                     "rows_found": len(body), "rows_named": len(named), "page": page,
                     "check": ";".join(checks) or "ok", "source": src})
        if "rows_do_not_add_up" in checks:
            continue                      # a misread table is not used row by row; the totals above still stand
        for r in body:
            anon = bool(ANON.match(r["name"]))
            relations.append({"company_id": code, "company_name": name, "direction": s["direction"], "relation": s["relation"],
                              "counterparty": f"{s['word']}（未披露名称）{r['name']}" if anon else r["name"],
                              "counterparty_code": "", "related_party": "未注明", "year": fy, "period": f"{fy}-12",
                              "amount_type": s["amount_type"], "amount_wan": to_wan(r["amount"], unit),
                              "share": round(r["share"] / 100, 4), "share_basis": f"占{fy}年年度{s['total']}总额（原表）",
                              "share_method": "原表披露", "goods": "", "source_type": "年报前五名表",
                              "source": f"{src} 第{table_page}页", "grade": "A" if not anon else "B",
                              "available_from": f"{int(fy) + 1}-04-30", "counterparty_named": "N" if anon else "Y"})
    return conc, relations


def main() -> None:
    names = {r["security_code"]: r["security_name"] for r in read(UNIVERSE)}
    notices = {(r["security_code"], r["fy"]): r["notice_date"] for r in read(SOURCES)}
    conc, relations = [], []
    for path in sorted(RAW.glob("*_*.pdf")):
        m = re.fullmatch(r"(\d{6})_(20\d\d)\.pdf", path.name)
        if not m:
            continue
        code, fy = m.groups()
        c, r = extract(path, code, names.get(code, code), fy, notices.get((code, fy), ""))
        conc += c
        relations += r
        status = "；".join(f"{x['side']}:{x['check']}" for x in c)
        print(f"[{code} {names.get(code, code)} FY{fy}] {status}; {len(r)} table rows")
    for path, fields, rows in ((CONC, CONC_FIELDS, conc), (TOP5, TOP5_FIELDS, relations)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    ok = sum(1 for c in conc if c.get("check") == "ok")
    print(f"\n{ok}/{len(conc)} company-year-sides fully read -> {CONC.relative_to(ROOT)}; "
          f"{len(relations)} counterparty rows ({sum(1 for r in relations if r['counterparty_named'] == 'Y')} named) "
          f"-> {TOP5.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
