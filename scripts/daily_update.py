"""Daily update: new announcements -> frozen extraction -> live graph -> fragility -> risk paths -> change report.

    python scripts/daily_update.py                 # full run (needs the project network: Sina, Eastmoney, LLM API)
    python scripts/daily_update.py --no-network    # rebuild graph, scores and report from what is already on disk
    python scripts/daily_update.py --since 2026-09-20

Steps
  1. announcement titles of all 40 companies published since the last run (Sina list, titles only)
  2. download them and extract with the FROZEN system (refuses to run on uncommitted src/schemas/prompts)
  3. rebuild data/chain/live from every frozen extraction (analysis corpus + daily + manually added);
     relationships out of their validity window are ignored on the evaluation date
  4. refresh fragility (new reports, today's prices, events) for the 24 mills + 16 chain companies
  5. propagate and compare today's key paths with the previous run -> data/live/report_<date>.md
Final-test documents are never downloaded (they are marked in the manifests and skipped).
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_financials import universe  # noqa: E402
from src.sources import readable  # noqa: E402

LIVE = ROOT / "data" / "live"
STATE = LIVE / "state.json"
CHAIN = ROOT / "data" / "chain" / "live"
PATTERN = {"related_party": "related_estimate", "guarantee": "guarantee_live", "capacity": "capacity", "pledge": "pledge"}


def run(*args: str) -> int:
    print("  $ python " + " ".join(args))
    return subprocess.run([sys.executable, *args], cwd=ROOT).returncode


def find_new(since: str, today: str) -> list[dict]:
    from scripts.find_analysis_corpus import classify, fetch_page, pdf_url, used_registry

    by_title, by_date = used_registry()
    found = []
    for company in universe():
        code, name = company["security_code"], company["security_name"]
        try:
            for page in range(1, 4):
                items = fetch_page(code, page)
                for item in items:
                    day, title = item["notice_date"], item["title"]
                    task = classify(title)
                    if since <= day <= today and task:
                        from scripts.find_analysis_corpus import norm
                        if by_title.get((code, norm(title))) or by_date.get((code, day)):
                            continue            # already used (dev / test / final test / corpus)
                        found.append({"code": code, "name": name, "day": day, "task": task, "title": title,
                                      "url": pdf_url(code, day, item["doc_id"]), "doc_id": item["doc_id"]})
                if not items or min(i["notice_date"] for i in items) < since:
                    break
                time.sleep(1)
        except Exception as error:
            print(f"  [skip] {code} {name}: {type(error).__name__}")
        time.sleep(0.5)
    return found


def write_selection(split: str, docs: list[dict]) -> None:
    path = ROOT / "data" / "manifests" / f"{split}_selection.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["holdout_id", "security_code", "security_name", "announcement_date", "target_pattern",
                    "announcement_title", "source_url", "notes"])
        for i, d in enumerate(docs, 1):
            w.writerow([f"{split}_{i:03d}", d["code"], d["name"], d["day"], PATTERN[d["task"]], d["title"], d["url"],
                        f"sina doc {d['doc_id']}; daily update"])


def read_paths(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {r["path"]: r for r in csv.DictReader(f)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--since")
    args = ap.parse_args()
    LIVE.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"last_checked": "2026-09-24"}
    today = date.today().isoformat()
    since = args.since or state["last_checked"]
    split = f"live_{today.replace('-', '')}"
    log = [f"# 每日更新 {today}", "", f"检查区间：{since} 至 {today}"]

    if not args.no_network:
        print("1/5 查找新公告标题 …")
        new = find_new(since, today)
        log.append(f"- 新公告：{len(new)} 份" + ("".join(f"\n  - {d['name']} {d['day']} 《{d['title']}》" for d in new)))
        if new:
            write_selection(split, new)
            print("2/5 下载并用冻结版系统提取 …")
            run("scripts/download_capacity_holdout.py", "--split", split)
            if (ROOT / "data" / "manifests" / f"{split}_sources.csv").exists():
                run("scripts/run_analysis_corpus.py", "--split", split)
    else:
        log.append("- 未联网：只用已有数据重建")

    print("3/5 重建实时图谱 …")
    sources = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "outputs").glob("*_freeze"))
               if p.name.startswith(("analysis", "live_", "manual"))]
    run("scripts/build_chain_inputs.py", "--src", *sources, "--out", "data/chain/live")

    print("4/5 更新承压评分 …")
    extras = [r["security_code"] for r in universe() if not (r["tier"] == "core" and r["core_analysis_target"] == "Y")]
    cmd = ["scripts/update_all.py", "--extra", *extras, "--signals", "data/chain/live/signals.csv"]
    run(*(cmd + (["--offline"] if args.no_network else [])))

    print("5/5 推导风险路径并对比上次 …")
    run("scripts/run_propagation.py", "--chain", "data/chain/live", "--snapshot", f"data/snapshots/{today}")
    now = read_paths(CHAIN / f"key_paths_{today}.csv")
    previous = sorted(p for p in CHAIN.glob("key_paths_*.csv") if p.stem.split("_")[-1] < today)
    before = read_paths(previous[-1]) if previous else {}
    added = [r for k, r in now.items() if k not in before]
    gone = [r for k, r in before.items() if k not in now]
    log += ["", f"## 风险路径变化（对比 {previous[-1].stem.split('_')[-1] if previous else '无上期'}）",
            f"当前关键路径 {len(now)} 条；新增 {len(added)}，消失 {len(gone)}。", ""]
    log += [f"- 新增：{r['path']}（得分 {r['score']}；起因 {readable(r['reason'], 80)}）" for r in sorted(added, key=lambda r: -float(r['score']))[:15]]
    log += [f"- 消失：{r['path']}" for r in gone[:15]]
    changes = ROOT / "data" / "snapshots" / today / "changes.md"
    if changes.exists():
        log += ["", changes.read_text(encoding="utf-8").replace("# ", "## ", 1)]
    report = LIVE / f"report_{today}.md"
    report.write_text("\n".join(log) + "\n", encoding="utf-8")
    if not args.no_network:
        state["last_checked"] = today
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成 -> {report.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
