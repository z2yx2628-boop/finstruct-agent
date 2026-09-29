"""Add amount kind, unified amount, quantity and the disclosed share to data/reference/prospectus_links.csv.

For every row the script re-reads the PDF page it came from (pdftotext -layout), finds the table line that carries
the row's number, and reads from the table itself:
  unit        the table's own unit (单位：万元 / 销售金额（亿元） / 销量（吨）), which overrides the extractor's guess
  amount_kind money | volume | foreign | unknown  (src/amounts.py) - a volume is never shown as an amount
  amount_wan  CNY amounts in 万元 (empty for volumes)
  quantity, quantity_unit   for volume tables (e.g. 河钢集团 2022 top-5 customers are in 吨)
  share, share_basis        the percentage printed in the same line, and the column it belongs to
                            (占采购成本总额百分比 / 占主营业务收入比例 / 占应收账款合计的比例 / 占比 ...)
Rows whose line cannot be found keep empty values and share_check = not_found. No number is guessed.

    python scripts/enrich_prospectus_links.py
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.amounts import kind, share_value, to_wan, unit_from_header  # noqa: E402

LINKS = ROOT / "data" / "reference" / "prospectus_links.csv"
PDFS = ROOT / "data" / "raw" / "prospectus"
TITLE = re.compile(r"前五大|前五名|前5名|前5大")
BASIS = re.compile(r"(占[一-龥（）()]{0,14}(?:比例|百分比|比重)|业务量占比|占比)")
NEW = ["amount_kind", "amount_wan", "quantity", "quantity_unit", "share", "share_basis", "share_check"]


@lru_cache(maxsize=None)
def pages(name: str) -> list[list[str]]:
    out = subprocess.run(["pdftotext", "-layout", str(PDFS / name), "-"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout
    return [p.splitlines() for p in out.split("\f")]


def grouped(amount: str) -> list[str]:
    whole, _, frac = amount.partition(".")
    g = f"{int(whole):,}" + (f".{frac}" if frac else "")
    forms = {amount, g}
    if frac and set(frac) == {"0"}:
        forms |= {whole, f"{int(whole):,}"}
    return sorted(forms, key=len, reverse=True)


def header_above(lines: list[str], i: int) -> tuple[str, int]:
    """Text from the table title (前五大...) down to the row; (header text, title line index)."""
    for j in range(i, max(-1, i - 40), -1):
        if TITLE.search(lines[j]):
            return " ".join(lines[j:i]), j
    return " ".join(lines[max(0, i - 8):i]), -1


def locate(row: dict) -> tuple[list[str], int, str] | None:
    """The table line with this row's number and name. When the same number appears in several tables
    (a prospectus may repeat a balance across years), the table whose title names the row's year wins."""
    try:
        doc = pages(row["source_file"])
    except FileNotFoundError:
        return None
    p = int(row["page"]) - 1
    name = re.sub(r"\s+", "", row["counterparty"])
    year = (row.get("period") or "")[:4]
    hits = []
    for q in (p, p + 1, p - 1):
        if not 0 <= q < len(doc):
            continue
        lines = (doc[q - 1] if q > 0 else []) + doc[q]
        offset = len(doc[q - 1]) if q > 0 else 0
        for i in range(offset, len(lines)):
            for form in grouped(row["amount"]):
                if re.search(rf"(?<![\d,.]){re.escape(form)}(?![\d,.])", lines[i]):
                    near = re.sub(r"\s+", "", "".join(lines[max(0, i - 2):i + 3]))
                    if name[:6] in near or name[-4:] in near:
                        _, t = header_above(lines, i)
                        title = lines[t] if t >= 0 else ""
                        hits.append((year in title, q == p, lines, i, form))
                    break
    if not hits:
        return None
    hits.sort(key=lambda h: (h[0], h[1]), reverse=True)
    return hits[0][2], hits[0][3], hits[0][4]


# what a share in each table is a share OF, when the column header only says 占比
STANDARD = {"supplier": "占采购额", "customer": "占销售收入", "receivable": "占应收账款余额", "prepayment": "占预付款项余额",
            "payable": "占应付账款余额", "contract_liability": "占合同负债余额"}


def enrich(row: dict) -> dict:
    out = {k: "" for k in NEW}
    found = locate(row)
    if not found:
        out["share_check"] = "not_found"
        unit = row["unit"]
    else:
        lines, i, form = found
        header, _ = header_above(lines, i)
        unit = unit_from_header(header) or row["unit"]
        after = lines[i].split(form, 1)[1]
        basis = BASIS.findall(header)
        has_pct_col = bool(basis) or "%" in header
        tokens = re.findall(r"\d[\d,]*\.?\d*%?", after)
        share = None
        for t in tokens:
            v = share_value(t)
            if v is not None and (t.endswith("%") or has_pct_col):
                share = v
                break
        if share is not None:
            out["share"] = f"{share:.4f}"
            specific = [re.sub(r"\s+", "", b) for b in basis if b not in ("占比",)]
            if kind(unit) == "volume":
                out["share_basis"] = "占销量" if row["role"] == "customer" else "占数量"
            else:
                out["share_basis"] = specific[-1] if specific else STANDARD.get(row["role"], "占比") + "（原表列名为“占比”，按表名推定）"
            out["share_check"] = "disclosed"
        else:
            out["share_check"] = "no_share_column" if not has_pct_col else "share_not_read"
    k = kind(unit)
    out["amount_kind"] = k
    if k == "money":
        out["amount_wan"] = f"{to_wan(row['amount'], unit):.2f}"
    elif k == "volume":
        out["quantity"], out["quantity_unit"] = row["amount"], unit
    row = dict(row, unit=unit)
    return {**row, **out}


def main() -> None:
    with LINKS.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    base = [c for c in rows[0] if c not in NEW]
    rows = [enrich({k: r[k] for k in base}) for r in rows]
    with LINKS.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=base + NEW, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(len(rows), "rows;", dict(Counter(r["amount_kind"] for r in rows)), dict(Counter(r["share_check"] for r in rows)))
    print("share bases:", dict(Counter(r["share_basis"] for r in rows if r["share_basis"])))


if __name__ == "__main__":
    main()
