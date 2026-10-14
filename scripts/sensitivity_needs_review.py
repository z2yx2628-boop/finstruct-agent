"""Sensitivity check (post hoc): do the live risk paths depend on documents flagged needs_review?

    python scripts/sensitivity_needs_review.py --as-of 2026-10-10

Builds the live graph twice from the same frozen extraction outputs -- (a) all documents, as the
live system does, and (b) only documents whose evidence check passed ("success") -- runs the same
propagation on the same fragility snapshot, and compares the key paths. Nothing in data/chain/live
is changed. A third build (c) keeps every document but drops only the records whose party name or
evidence excerpt cannot be found anywhere in the document text (an excerpt found on another page --
page number wrong, content right -- is kept). The build folders data/chain/sensitivity_* are
reproducible and not committed; the comparison goes to data/eval/needs_review_sensitivity_<date>.json.
Results: docs/needs_review_sensitivity.md.
"""
import argparse
import csv
import glob
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.chain_inputs import EDGE_FIELDS, SIGNAL_FIELDS, as_row, doc_key, doc_kind, edges_from, industry_edges, signals_from  # noqa: E402


def statuses() -> dict[str, str]:
    """file stem -> extraction status, from every run log of the frozen system."""
    out = {}
    for f in glob.glob(str(ROOT / "outputs" / "*_freeze" / "run_log.json")):
        for r in json.loads(Path(f).read_text(encoding="utf-8"))["runs"].values():
            if r.get("prediction"):
                out[Path(r["prediction"].replace("\\", "/")).stem] = r["status"]
    for f in glob.glob(str(ROOT / "experiments" / "*_r1" / "batch_run.json")):
        for r in json.loads(Path(f).read_text(encoding="utf-8")).get("runs", []):
            if r.get("prediction"):
                out.setdefault(Path(r["prediction"].replace("\\", "/")).stem, r["status"])
    for f in glob.glob(str(ROOT / "outputs" / "final_*" / "*" / "run_log.json")):
        st = json.loads(Path(f).read_text(encoding="utf-8")).get("status")
        if st:
            out.setdefault(Path(f).parents[1].name, st)
    return out


ROOT_WIN = "E:\\金融人工智能比赛9..10-10.18\\"
PARTY = {"counterparty", "guarantor", "guaranteed_party", "creditor", "pledgee", "shareholder_name"}
squash = lambda s: "".join(str(s or "").split())


def run_dirs() -> dict[str, Path]:
    """file stem -> run directory holding pages.json and evidence_report.json."""
    out = {}
    logs = [(f, json.loads(Path(f).read_text(encoding="utf-8"))["runs"].values()) for f in glob.glob(str(ROOT / "outputs" / "*_freeze" / "run_log.json"))]
    logs += [(f, json.loads(Path(f).read_text(encoding="utf-8")).get("runs", [])) for f in glob.glob(str(ROOT / "experiments" / "*_r1" / "batch_run.json"))]
    for _, runs in logs:
        for r in runs:
            if r.get("prediction") and r.get("run_directory"):
                out.setdefault(Path(r["prediction"].replace("\\", "/")).stem, ROOT / r["run_directory"].replace(ROOT_WIN, "").replace("\\", "/"))
    for f in glob.glob(str(ROOT / "outputs" / "final_*" / "*" / "run_log.json")):
        out.setdefault(Path(f).parents[1].name, Path(f).parent)
    return out


def unsupported(run_dir: Path, tally: Counter) -> tuple[set, set]:
    """(record indexes, event indexes) whose party name or evidence text cannot be found anywhere in the document.
    An evidence text found on another page (page number wrong, content right) is kept."""
    rep, pages = run_dir / "evidence_report.json", run_dir / "pages.json"
    if not rep.exists() or not pages.exists():
        tally["no_report"] += 1
        return set(), set()
    text = squash(" ".join(p.get("text", "") for p in json.loads(pages.read_text(encoding="utf-8"))))
    rec, ev = set(), set()
    for i in json.loads(rep.read_text(encoding="utf-8")).get("issues", []):
        field, reason = i.get("field"), i.get("reason", i.get("check", ""))
        idx = i.get("record_index") if i.get("record_index") is not None else i.get("event_index")
        target = rec if i.get("record_index") is not None else ev
        if field == "evidence_text":
            if squash(i.get("value")) and squash(i.get("value")) in text:
                tally["evidence_on_other_page"] += 1
                continue
            tally["evidence_not_in_document"] += 1
        elif field in PARTY and i.get("value"):
            tally["party_not_found"] += 1
        else:
            tally["other_issue_kept"] += 1
            continue
        if idx is not None:
            target.add(idx)
    return rec, ev


def build(sources: list[Path], out: Path, keep, prune=None) -> Counter:
    edges, signals, seen, n = [], [], set(), Counter()
    for path in sorted(p for src in sources for p in src.rglob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(doc, dict) or "security_code" not in doc or doc_key(doc) in seen:
            continue
        seen.add(doc_key(doc))
        ok, st = keep(path)
        n[st] += 1
        if not ok:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if prune:
            doc = prune(path, doc, n)
        e, _ = edges_from(doc, rel)
        edges += e
        signals += signals_from(doc, rel)
    n["edges_disclosed"] = len(edges)
    edges += industry_edges()
    out.mkdir(parents=True, exist_ok=True)
    for name, rows, fields in (("edges.csv", edges, EDGE_FIELDS), ("signals.csv", signals, SIGNAL_FIELDS)):
        with (out / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(as_row(r) for r in rows)
    return n


def paths(chain: Path, as_of: str) -> list[dict]:
    with (chain / f"key_paths_{as_of}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", required=True)
    args = ap.parse_args()
    st = statuses()
    sources = [p for p in sorted((ROOT / "outputs").glob("*_freeze")) if p.name.startswith(("analysis", "live_", "manual"))]
    stem = lambda p: p.stem
    look = lambda p: st.get(stem(p), "manual" if "manual_freeze" in p.as_posix() else "unknown")
    a, b = ROOT / "data/chain/sensitivity_all", ROOT / "data/chain/sensitivity_success"
    na = build(sources, a, lambda p: (True, look(p)))
    nb = build(sources, b, lambda p: (look(p) in ("success", "manual"), look(p)))
    dirs, tally = run_dirs(), Counter()

    def prune(path, doc, n):
        rd = dirs.get(path.stem)
        if rd is None:
            return doc
        rec, ev = unsupported(rd, tally)
        doc = dict(doc)
        if rec and doc.get("transactions"):
            n["records_dropped"] += sum(1 for k in range(len(doc["transactions"])) if k in rec)
            doc["transactions"] = [t for k, t in enumerate(doc["transactions"]) if k not in rec]
        if ev and doc.get("events"):
            n["events_dropped"] += sum(1 for k in range(len(doc["events"])) if k in ev)
            doc["events"] = [t for k, t in enumerate(doc["events"]) if k not in ev]
        return doc
    c3 = ROOT / "data/chain/sensitivity_record"
    nc = build(sources, c3, lambda p: (True, look(p)), prune)
    for c in (a, b, c3):
        subprocess.run([sys.executable, "scripts/run_propagation.py", "--chain", c.relative_to(ROOT).as_posix(),
                        "--snapshot", f"data/snapshots/{args.as_of}"], cwd=ROOT, check=True, capture_output=True)
    pa, pb, pc = paths(a, args.as_of), paths(b, args.as_of), paths(c3, args.as_of)
    live = ROOT / "data/chain/live" / f"key_paths_{args.as_of}.csv"
    same_as_live = live.exists() and live.read_bytes() == (a / f"key_paths_{args.as_of}.csv").read_bytes()
    ka, kb = [r["path"] for r in pa], {r["path"] for r in pb}
    res = {"as_of": args.as_of, "docs": dict(na), "docs_kept": dict(nb), "paths_all": len(pa), "paths_success": len(pb),
           "same_as_live": same_as_live}
    for k in (5, 10, 20):
        top = ka[:k]
        res[f"top{k}_kept"] = sum(p in kb for p in top)
    res["all_kept"] = sum(p in kb for p in ka)
    res["new_in_success"] = len(kb - set(ka))
    seeds_a, seeds_b = {r["seed"] for r in pa}, {r["seed"] for r in pb}
    res["seeds_all"], res["seeds_success"], res["seeds_kept"] = len(seeds_a), len(seeds_b), len(seeds_a & seeds_b)
    kc = {r["path"] for r in pc}
    res["record_level"] = {"docs": dict(nc), "issues": dict(tally), "paths": len(pc),
                           **{f"top{k}_kept": sum(p in kc for p in ka[:k]) for k in (5, 10, 20)},
                           "all_kept": sum(p in kc for p in ka), "new": len(kc - set(ka)),
                           "seeds": len({r["seed"] for r in pc})}
    res["lost_record_level"] = [(r["rank"], r["path"], r["rules"]) for r in pa if r["path"] not in kc]
    res["top10"] = [(r["rank"], r["path"], r["rules"], r["path"] in kb) for r in pa[:10]]
    res["lost"] = [(r["rank"], r["path"], r["rules"]) for r in pa if r["path"] not in kb][:30]
    print(json.dumps(res, ensure_ascii=False, indent=1))
    (ROOT / "data/eval" / f"needs_review_sensitivity_{args.as_of}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
