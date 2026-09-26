"""Helper for annotating the final-test Gold. It never runs the extraction model.

    python scripts/final_gold.py init       # 8 empty Gold templates + README draft (never overwrites)
    python scripts/final_gold.py text       # page text of each source (PDF pages / web [P] blocks) for annotating
    python scripts/final_gold.py check      # schema + evidence check of the Gold you wrote
    python scripts/final_gold.py lock       # write gold_manifest.lock (run once, after check passes)

Rules: docs/annotation_guidelines.md, prompts/related_party_extraction_v1.txt and the
"Final-test scope rules" section of data/gold/final_test/README.md (written before annotation).
"""
import csv
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RAW = ROOT / "data" / "raw" / "final_test"
GOLD = ROOT / "data" / "gold" / "final_test"
TEXT = GOLD / "source_text"
SYSTEM_COMMIT = "8a0abba"          # extraction-freeze-2026-09-24


def documents() -> list[dict]:
    with (ROOT / "data" / "manifests" / "final_test_selection.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    docs = []
    for r in rows:
        src = sorted(RAW.glob(f"{r['holdout_id']}_*"))
        src = [p for p in src if p.suffix.lower() in (".pdf", ".html", ".htm", ".docx", ".doc")]
        docs.append({"id": r["holdout_id"], "code": r["security_code"], "name": r["security_name"],
                     "date": r["announcement_date"], "pattern": r["target_pattern"],
                     "title": r["announcement_title"], "source": src[0] if src else None})
    web = RAW / "final_web_001.html"
    if web.exists():
        docs.append({"id": "final_web_001", "code": None, "name": None, "date": None,
                     "pattern": "capacity_maintenance", "title": "webpage", "source": web})
    return docs


def task_of(doc: dict) -> str:
    return "capacity" if doc["pattern"].startswith("capacity") else "related_party"


def gold_path(doc: dict) -> Path:
    stem = doc["source"].stem if doc["source"] else doc["id"]
    return GOLD / f"{stem}.json"


def template(doc: dict) -> dict:
    if task_of(doc) == "capacity":
        return {"security_code": doc["code"], "security_name": doc["name"], "company_name": None,
                "announcement_number": None, "announcement_date": None, "events": []}
    return {"security_code": doc["code"], "security_name": doc["name"], "company_name": None,
            "announcement_number": None, "announcement_date": None, "estimate_year": None,
            "total_estimated_amount": None, "total_estimated_unit": None,
            "requires_shareholder_approval": None, "transactions": []}


def init() -> None:
    GOLD.mkdir(parents=True, exist_ok=True)
    for doc in documents():
        if not doc["source"]:
            print(f"[missing source] {doc['id']}")
            continue
        path = gold_path(doc)
        if path.exists():
            print(f"[kept] {path.name} already exists")
            continue
        path.write_text(json.dumps(template(doc), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[new]  {path.name}")


def pages(doc: dict):
    from src.document_parser import parse_document
    return parse_document(doc["source"]).pages


def text() -> None:
    TEXT.mkdir(parents=True, exist_ok=True)
    for doc in documents():
        if not doc["source"]:
            continue
        out = TEXT / f"{doc['source'].stem}.txt"
        parts = [f"===== 第 {p.page} 页 =====\n{p.text}" for p in pages(doc)]
        out.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
        print(f"{out.relative_to(ROOT)}  ({len(parts)} 页)")


def squeeze(s: str) -> str:
    return re.sub(r"\s+", "", str(s))


def check() -> bool:
    from schemas.capacity import CapacityDocument
    from schemas.related_party import RelatedPartyDocument
    ok = True
    for doc in documents():
        path = gold_path(doc) if doc["source"] else None
        if not path or not path.exists():
            print(f"[missing] {doc['id']}")
            ok = False
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        model = CapacityDocument if task_of(doc) == "capacity" else RelatedPartyDocument
        try:
            model.model_validate(data)
        except Exception as exc:          # schema errors are printed, not raised
            print(f"[schema] {path.name}: {exc}")
            ok = False
            continue
        page_text = {p.page: squeeze(p.text) for p in pages(doc)}
        records = data.get("transactions", data.get("events", []))
        items = []
        for i, r in enumerate(records, 1):
            items.append((f"#{i}", r))
            for j, c in enumerate(r.get("capacity_changes", []) + r.get("environmental_metrics", []), 1):
                items.append((f"#{i}.{j}", c))
        bad = 0
        for label, r in items:
            if r.get("confidence") != 1.0:
                print(f"[confidence] {path.name} {label}: Gold confidence must be 1.0")
                bad += 1
            ev = squeeze(r.get("evidence_text", ""))
            if ev not in page_text.get(r.get("source_page"), ""):
                where = [p for p, t in page_text.items() if ev and ev in t]
                hint = f"（在第 {where} 页找到）" if where else "（任何页都找不到，检查是否改写或跨页）"
                print(f"[evidence] {path.name} {label}: 证据不在第 {r.get('source_page')} 页{hint}")
                bad += 1
        ok &= bad == 0
        print(f"[{'ok' if bad == 0 else 'fix'}] {path.name}: {len(records)} 条记录，{bad} 个问题")
    return ok


def lock() -> None:
    lock_path = GOLD / "gold_manifest.lock"
    if lock_path.exists():
        sys.exit("gold_manifest.lock already exists: a frozen Gold is never rewritten (make a -v2 instead).")
    if not check():
        sys.exit("check failed: fix the Gold first.")
    files, total = [], 0
    for doc in documents():
        path = gold_path(doc)
        data = json.loads(path.read_text(encoding="utf-8"))
        n = len(data.get("transactions", data.get("events", [])))
        total += n
        files.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "records": n,
                      "source_sha256": hashlib.sha256(doc["source"].read_bytes()).hexdigest()})
    manifest = {"version": "final-test-gold-v1", "frozen_at": date.today().isoformat(), "hash_algorithm": "sha256",
                "document_count": len(files), "record_count": total,
                "system_under_test_commit": SYSTEM_COMMIT, "system_under_test_tag": "extraction-freeze-2026-09-24",
                "files": files}
    lock_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"-> {lock_path.relative_to(ROOT)}: {len(files)} documents, {total} records")


if __name__ == "__main__":
    {"init": init, "text": text, "check": check, "lock": lock}[sys.argv[1] if len(sys.argv) > 1 else "check"]()
