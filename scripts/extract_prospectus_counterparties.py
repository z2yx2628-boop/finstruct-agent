"""Extract named counterparties from bond-prospectus "前五大/前五名" tables (suppliers, customers, receivables,
prepayments, payables, contract liabilities) into a review CSV. Rule-based, no model call.

    python scripts/extract_prospectus_counterparties.py
Input : data/raw/prospectus/*.pdf  (text via pdftotext -layout; pages split on form feeds)
Output: data/reference/prospectus_counterparties_candidates.csv  (every row needs a human check: verified=N)
Anonymised rows (单位一 / 客户 1 / A / 第一名 ...) are skipped: they name no counterparty.
"""
import csv
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "prospectus"
OUT = ROOT / "data" / "reference" / "prospectus_counterparties_candidates.csv"
KIND = [("应收账款", "receivable"), ("其他应收", "other_receivable"), ("预付", "prepayment"), ("应付账款", "payable"),
        ("合同负债", "contract_liability"), ("供应商", "supplier"), ("客户", "customer")]
TITLE = re.compile(r"(前五大|前五名|前5名|前5大)")
ANON = re.compile(r"^(单位|客户|供应商|债务人|公司)?\s*[一二三四五六七八九十0-9A-Za-z]{1,2}\s*$|^第[一二三四五]名$|^[A-ER]$")
NUM = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+)(?![\d.])")
NAME = re.compile(r"[一-龥A-Za-z（）()·&\s]{4,}")


def pages(pdf: Path) -> list[str]:
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, errors="replace").stdout
    return txt.split("\f")


def kind_of(title: str) -> str:
    for key, k in KIND:
        if key in title:
            return k
    return "other"


def rows_after(lines: list[str], start: int) -> list[tuple[str, str, str]]:
    """(name, amount, related) rows between a table title and its 合计 line; wrapped names are joined."""
    out, carry = [], ""
    for line in lines[start + 1:start + 40]:
        s = line.strip()
        if not s or re.fullmatch(r"\d{1,4}", s):
            continue
        if s.startswith("合计") or re.search(r"^\s*合\s*计", s) or TITLE.search(s) and out:
            break
        nums = NUM.findall(s)
        text = re.sub(r"\s{2,}", "|", s)
        parts = [p for p in text.split("|") if p.strip()]
        name_parts = [p for p in parts if NAME.fullmatch(p.strip()) and not re.search(r"单位|余额|金额|比例|占比|序号|名称|性质|关联|账龄|坏账|年末|月末", p)]
        if not nums:
            if name_parts:
                carry += "".join(name_parts)
            continue
        name = (carry + "".join(p for p in name_parts if not re.search(r"是|否|关联方|第三方|货款|工程款|往来款|借款", p))).strip()
        carry = ""
        related = "是" if re.search(r"(?<!非)关联方|\s是(\s|$)", s) else "否" if re.search(r"非关联|第三方|\s否(\s|$)", s) else ""
        name = re.sub(r"^\d+\s*", "", name)
        if name and not ANON.match(name) and len(name) >= 4:
            out.append((name, nums[0], related))
    return out


def main() -> None:
    records = []
    for pdf in sorted(SRC.glob("*.pdf")):
        doc = pages(pdf)
        for pno, page in enumerate(doc, 1):
            lines = page.splitlines()
            for i, line in enumerate(lines):
                if not TITLE.search(line) or len(line.strip()) > 60 or "占" in line and "比例" in line and "表" not in line:
                    continue
                title = line.strip()
                spill = lines + (doc[pno].splitlines() if pno < len(doc) else [])
                for name, amount, related in rows_after(spill, i):
                    unit = "亿元" if "亿元" in " ".join(spill[i:i + 4]) else "万元"
                    records.append({"file": pdf.name, "page": pno, "table": title, "kind": kind_of(title), "counterparty": name,
                                    "amount": amount.replace(",", ""), "unit": unit, "related_party": related, "verified": "N"})
    seen, unique = set(), []
    for r in records:
        key = (r["file"], r["table"], r["counterparty"], r["amount"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(unique[0]))
        w.writeheader()
        w.writerows(unique)
    print(f"{len(unique)} named counterparties from {len({r['file'] for r in unique})} files -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
