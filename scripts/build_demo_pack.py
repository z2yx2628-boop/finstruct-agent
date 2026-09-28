"""Offline demo pack: a few real announcements with the frozen system's saved extraction, so the demo
(分析新公告) runs with no model API and no network. Re-run after changing the list.

    python scripts/build_demo_pack.py
Copies each source file and its saved prediction into data/demo/ and writes data/demo/manifest.json
(sha256 of every file). src/analyze.py replays a prediction when the uploaded file's sha256 is in the
manifest and the model is not used (offline mode, or the model call fails).
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "demo"
# id, label, task, source, saved prediction, evaluation date, chain, why it is in the demo
CASES = [
    ("antai_guarantee", "安泰集团：为山西新泰钢铁提供担保（安泰回测）", "guarantee",
     "data/raw/backtest_antai/backtest_antai_006_600408_guarantee_backtest.pdf",
     "outputs/backtest_antai_freeze/guarantee/backtest_antai_006_600408_guarantee_backtest.json",
     "2025-01-31", "data/chain/backtest_antai_fix1", "回测：违约事件前 6 天；校准后担保路径排第 1（原始回测排第 2，记为部分通过）"),
    ("linggang_guarantee", "凌钢股份：为控股股东凌钢集团提供担保（凌钢回测）", "guarantee",
     "data/raw/backtest_linggang/backtest_linggang_033_600231_guarantee_backtest.pdf",
     "outputs/backtest_linggang_freeze/guarantee/backtest_linggang_033_600231_guarantee_backtest.json",
     "2024-04-30", "data/chain/backtest_linggang_fix1", "样本外正例：亏损披露前约 11 个月"),
    ("fangda_guarantee", "方大特钢：为方大炭素提供担保（方大回测）", "guarantee",
     "data/raw/analysis/analysis_063_600507_guarantee_related.pdf",
     "outputs/analysis_freeze/guarantee/analysis_063_600507_guarantee_related.json",
     "2025-02-28", "data/chain/analysis_v1_fix1", "样本外反例：有关联担保但不误报"),
    ("linggang_pledge", "凌钢股份：股东九江萍钢质押所持股份", "pledge",
     "data/raw/analysis/analysis_044_600231_pledge.pdf",
     "outputs/analysis_freeze/pledge/analysis_044_600231_pledge.json",
     "2025-01-31", "data/chain/live", "质押严重度按股东持股比例（10.91% 股东，判为中）"),
    ("ansteel_related", "鞍钢股份：2026 年度日常关联交易预计（最终测试文档）", "related_party",
     "data/raw/final_test/final_001_000898_related_estimate.pdf",
     "outputs/final_test/r1/related_party/predictions_fix1/final_001_000898_related_estimate.json",
     "2026-09-27", "data/chain/live", "最终盲测文档之一（修复后抽取结果）"),
    ("fangda_maintenance", "方大特钢“一条龙”检修（新闻网页）", "capacity",
     "data/raw/final_test/final_web_001.html",
     "outputs/final_test/r1/capacity/predictions/final_web_001.json",
     "2026-09-27", "data/chain/live", "网页格式；检修事件"),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    DEMO.mkdir(parents=True, exist_ok=True)
    manifest, missing = [], []
    for cid, label, task, source, prediction, as_of, chain, why in CASES:
        src, pred = ROOT / source, ROOT / prediction
        if not src.exists() or not pred.exists():
            missing.append(f"{cid}: {'source' if not src.exists() else 'prediction'} not found")
            continue
        src_copy = DEMO / f"{cid}{src.suffix.lower()}"
        pred_copy = DEMO / f"{cid}.prediction.json"
        shutil.copy2(src, src_copy)
        shutil.copy2(pred, pred_copy)
        meta = src.with_suffix(".meta.json")
        if meta.exists():                                  # web pages carry their publish date / URL here
            shutil.copy2(meta, DEMO / f"{cid}.meta.json")
        manifest.append({"id": cid, "label": label, "task": task, "source": src_copy.relative_to(ROOT).as_posix(),
                         "source_sha256": sha(src_copy), "prediction": pred_copy.relative_to(ROOT).as_posix(),
                         "prediction_from": prediction, "as_of": as_of, "chain": chain, "why": why})
    (DEMO / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(manifest)} demo cases -> data/demo/manifest.json")
    for m in missing:
        print(f"[missing] {m}")
    if missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
