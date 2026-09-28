"""Machine check of data/reference/prospectus_links.csv against the PDF text: is the counterparty name and the
amount printed on the page given (or the next page, for tables that break)? Writes column `page_check`:
  ok        both found on that page (or the next)
  name_only the name is there but not the amount
  missing   the name is not found (row needs a person)
A person still signs off (verified = Y); this only tells which rows are safe and which need attention.
    python scripts/check_prospectus_links.py
"""
import csv
import re
import subprocess
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINKS = ROOT / "data" / "reference" / "prospectus_links.csv"


@lru_cache(maxsize=None)
def pages(name: str) -> list[str]:
    out = subprocess.run(["pdftotext", "-layout", str(ROOT / "data" / "raw" / "prospectus" / name), "-"],
                         capture_output=True, text=True, errors="replace").stdout
    return [re.sub(r"\s+", "", p) for p in out.split("\f")]


def check(row: dict) -> str:
    try:
        doc = pages(row["source_file"])
    except FileNotFoundError:
        return "no_pdf"
    i = int(row["page"]) - 1
    text = "".join(doc[i:i + 2]) if i < len(doc) else ""
    name = re.sub(r"\s+", "", row["counterparty"])
    amount = row["amount"]
    whole, _, frac = amount.partition(".")
    grouped = f"{int(whole):,}" + (f".{frac}" if frac else "")
    has_name = name in text or (len(name) > 8 and name[:8] in text and name[-4:] in text)
    has_amount = amount in text or grouped in text
    return "ok" if has_name and has_amount else "name_only" if has_name else "missing"


rows = list(csv.DictReader(LINKS.open(encoding="utf-8-sig", newline="")))
for r in rows:
    r["page_check"] = check(r)
fields = list(rows[0])
with LINKS.open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)
from collections import Counter  # noqa: E402
print(Counter(r["page_check"] for r in rows))
for r in rows:
    if r["page_check"] != "ok":
        print(r["page_check"], r["issuer"], r["counterparty"], r["amount"], "p", r["page"])
