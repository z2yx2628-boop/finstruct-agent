"""Export and import exposure from the annual reports already downloaded (data/raw/annual_reports/).

1. Overseas revenue share (出口 / 境外收入): the "分地区" rows of the revenue breakdown in the MD&A
   -> data/reference/annual_overseas_revenue.csv
   A row counts as overseas when its label says so (境外, 国外, 海外, 出口, 国际, a foreign region), or when it is
   "其他地区" in a table that splits 中国大陆 / 境内 from the rest. A table that only lists domestic regions
   (华东, 西南 ...) says nothing about exports: overseas_share stays empty with check = no_domestic_foreign_split.
2. Iron-ore supply (进口依赖): the "铁矿石供应情况" table that steel companies on the Shanghai exchange must publish
   (自供 / 国内采购 / 国外进口: tonnes and money, this year and last year)
   -> data/reference/annual_iron_ore_supply.csv
   Tonnes and money stay in separate columns; money goes through src/amounts.py to 万元.

Nothing is guessed: a figure that is not found stays empty and the row says why.

    python scripts/extract_annual_trade.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.extract_annual_top5 import RAW, UNIVERSE, pages, read  # noqa: E402
from src.amounts import to_wan  # noqa: E402
from src.quarterly import parse_abstract  # noqa: E402

QDIR = ROOT / "data" / "external" / "financials" / "quarterly"


def revenue_wan(code: str, fy: str) -> float | None:
    """Annual revenue from the Sina abstract, to catch a region table whose wrapped numbers were misread."""
    path = QDIR / f"{code}_abstract.csv"
    if not path.exists():
        return None
    with path.open(encoding="utf-8-sig", newline="") as f:
        p = parse_abstract(list(csv.reader(f))).get(f"{fy}1231", {})
    return p["revenue"] / 1e4 if p.get("revenue") else None

OVERSEAS = ROOT / "data" / "reference" / "annual_overseas_revenue.csv"
ORE = ROOT / "data" / "reference" / "annual_iron_ore_supply.csv"
NUM = r"-?[\d,]+(?:\.\d+)?"
FOREIGN = re.compile(r"境外|国外|海外|出口|国际|外销|亚洲|欧洲|美洲|非洲|大洋洲|中东|东南亚|港澳台|其他国家")
DOMESTIC = re.compile(r"中国大陆|境内|国内|内销|中国境内")
REGION_WORD = re.compile(r"华东|华南|华北|华中|西南|西北|东北|东部|西部|南部|北部|中部|省|市|区域|地区")
STOP = re.compile(r"分销售模式|分行业|分产品|说明|占公司营业收入|产销量|^\s*\(?\d\)|^（\d）")
OV_FIELDS = ["company_id", "company_name", "fy", "overseas_share", "overseas_wan", "total_wan", "overseas_labels",
             "all_labels", "page", "check", "source"]
ORE_FIELDS = ["company_id", "company_name", "fy", "self_t", "domestic_t", "import_t", "total_t", "import_share_t",
              "self_wan", "domestic_wan", "import_wan", "total_wan", "import_share_amount", "unit", "page", "check", "source"]


def numbers(text: str) -> list[float | None]:
    """Column values of a table line: numbers and '-' (an empty cell) in order."""
    out = []
    for tok in re.findall(rf"(?<![\w.]){NUM}(?![\w.])|(?<=\s)[-/](?=\s|$)", text):
        out.append(None if tok in ("-", "/") else float(tok.replace(",", "")))
    return out


def region_rows(texts: list[str]) -> tuple[list[tuple[str, float, float | None]], str | None, int] | None:
    """(label, revenue, share of revenue or None) rows of the first 分地区 block, the unit, the page."""
    lines = [(i + 1, line) for i, t in enumerate(texts) for line in t.splitlines()]
    for k, (page, line) in enumerate(lines):
        flat = re.sub(r"\s+", "", line)
        if not (flat.startswith("分地区") or flat.startswith("主营业务分地区情况")):
            continue
        before = " ".join(l for _, l in lines[max(0, k - 40):k])
        unit = next(iter(re.findall(r"单位[:：]\s*(?:人民币)?\s*(百万元|千元|万元|亿元|元)", before)[-1:]), None)
        rows = []
        for _, body in lines[k + 1:k + 25]:
            flat_body = re.sub(r"\s+", "", body)
            if rows and STOP.search(flat_body):
                break
            m = re.match(r"^\s*([一-龥A-Za-z（）()、]{2,20}?)\s+(" + NUM + r")(.*)$", body)
            if not m or re.search(r"营业收入|营业成本|毛利率|分地区|合计|小计|单位", m.group(1)):
                continue
            rest = m.group(3)
            share = re.search(r"(\d+(?:\.\d+)?)%", rest)
            rows.append((m.group(1).strip(), float(m.group(2).replace(",", "")), float(share.group(1)) / 100 if share else None))
        if rows:
            return rows, unit, page
    return None


def overseas(path: Path, code: str, name: str, fy: str) -> dict:
    src = f"{fy}年年度报告"
    base = {"company_id": code, "company_name": name, "fy": fy, "source": src}
    got = region_rows(pages(path))
    if not got:
        return dict(base, check="region_table_not_found")
    rows, unit, page = got
    labels = [r[0] for r in rows]
    has_domestic = any(DOMESTIC.search(l) for l in labels)
    abroad = [r for r in rows if FOREIGN.search(r[0]) or (has_domestic and re.fullmatch(r"其他(地区|国家和地区)?", r[0]))]
    total = sum(r[1] for r in rows)
    out = dict(base, all_labels="、".join(labels), page=page)
    if not abroad:
        explicit_zero = has_domestic and len(rows) == 1
        if explicit_zero or has_domestic:
            return dict(out, overseas_share=0.0, total_wan=round(to_wan(total, unit) or 0, 2) if unit else "",
                        overseas_wan=0.0, check="only_domestic_reported")
        return dict(out, check="no_domestic_foreign_split" if all(REGION_WORD.search(l) for l in labels) else "no_overseas_row")
    amount = sum(r[1] for r in abroad)
    shares = [r[2] for r in abroad]
    share = sum(shares) if all(s is not None for s in shares) else (amount / total if total else None)
    rev = revenue_wan(code, fy)
    total_w = to_wan(total, unit) if unit else None
    if share is None or not 0 < share <= 1 or (rev and total_w and not 0.5 <= total_w / rev <= 1.5):
        return dict(out, overseas_labels="、".join(r[0] for r in abroad), check="misread_table")
    return dict(out, overseas_share=round(share, 4), overseas_labels="、".join(r[0] for r in abroad),
                overseas_wan=round(to_wan(amount, unit), 2) if unit and to_wan(amount, unit) is not None else "",
                total_wan=round(to_wan(total, unit), 2) if unit and to_wan(total, unit) is not None else "", check="ok")


def iron_ore(path: Path, code: str, name: str, fy: str) -> dict | None:
    texts = pages(path)
    lines = [(i + 1, line) for i, t in enumerate(texts) for line in t.splitlines()]
    base = {"company_id": code, "company_name": name, "fy": fy, "source": f"{fy}年年度报告"}
    for k, (page, line) in enumerate(lines):
        if "铁矿石供应情况" not in re.sub(r"\s+", "", line):
            continue
        block = [l for _, l in lines[k:k + 16]]
        if any("不适用" in re.sub(r"\s+", "", l) and "√不适用" in re.sub(r"\s+", "", l) for l in block[:2]):
            return dict(base, page=page, check="not_applicable")
        unit = next(iter(re.findall(r"单位[:：]\s*(?:人民币)?\s*(百万元|千元|万元|亿元|元)", " ".join(block))), None)
        vals = {}
        for l in block:
            flat = re.sub(r"\s+", "", l)
            for key, word in (("self", "自供"), ("domestic", "国内采购"), ("import", "国外进口"), ("total", "合计")):
                if flat.startswith(word) and key not in vals:
                    nums = numbers(l)
                    if len(nums) >= 3:            # tonnes this year, tonnes last year, money this year[, money last year]
                        vals[key] = (nums[0], nums[2])
        if "import" not in vals:
            return dict(base, page=page, check="rows_not_read")
        t = {k: v[0] for k, v in vals.items()}
        a = {k: v[1] for k, v in vals.items()}
        total_t = t.get("total") or sum(v or 0 for k, v in t.items() if k != "total")
        total_a = a.get("total") or sum(v or 0 for k, v in a.items() if k != "total")
        w = lambda v: round(to_wan(v, unit), 2) if v is not None and unit and to_wan(v, unit) is not None else ""  # noqa: E731
        return dict(base, page=page, unit=unit or "", check="ok" if unit else "unit_not_found",
                    self_t=t.get("self") or 0, domestic_t=t.get("domestic") or 0, import_t=t.get("import") or 0, total_t=total_t,
                    import_share_t=round((t.get("import") or 0) / total_t, 4) if total_t else "",
                    self_wan=w(a.get("self") or 0), domestic_wan=w(a.get("domestic") or 0), import_wan=w(a.get("import") or 0),
                    total_wan=w(total_a), import_share_amount=round((a.get("import") or 0) / total_a, 4) if total_a else "")
    return None


def main() -> None:
    names = {r["security_code"]: r["security_name"] for r in read(UNIVERSE)}
    ov, ore = [], []
    for path in sorted(RAW.glob("*_*.pdf")):
        m = re.fullmatch(r"(\d{6})_(20\d\d)\.pdf", path.name)
        if not m:
            continue
        code, fy = m.groups()
        name = names.get(code, code)
        ov.append(overseas(path, code, name, fy))
        o = iron_ore(path, code, name, fy)
        if o:
            ore.append(o)
        print(f"[{code} {name} FY{fy}] overseas {ov[-1].get('overseas_share', '—')} ({ov[-1]['check']}); "
              f"iron ore {'import ' + str(o.get('import_share_t', '—')) + ' of tonnes' if o else 'no table'}")
    for path, fields, rows in ((OVERSEAS, OV_FIELDS, ov), (ORE, ORE_FIELDS, ore)):
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    print(f"\n{sum(1 for r in ov if r['check'] in ('ok', 'only_domestic_reported'))}/{len(ov)} overseas shares -> {OVERSEAS.relative_to(ROOT)}")
    print(f"{sum(1 for r in ore if r['check'] == 'ok')} iron-ore supply tables -> {ORE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
