"""分析新公告 page helpers (display only): the agent's ten steps, plain-language demo cases, the model's status,
and the announcements the daily update picked up recently."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PIPELINE = [("识别类型", "这是担保、关联交易、质押还是检修公告"), ("选择工具", "按类型选对应的抽取模板"),
            ("结构化抽取", "大模型把原文变成字段，每条带页码"), ("检查证据", "核对引用的原句确实在原文里"),
            ("实体解析", "把公司名对到企业库"), ("入图决策", "证据不全的转人工复核"),
            ("承压查询", "相关企业扛不扛得住"), ("计算敞口", "担保占净资产多少"),
            ("传导推演", "风险会传给谁"), ("生成报告", "一句结论 + 原文依据")]

# demo case id -> (type tag, what it shows in plain words, order)
CASES = {"antai_guarantee": ("担保", "回测：安泰违约前 6 天，系统已把这条担保路径列为优先核查（校准后第 1）", 0),
         "linggang_guarantee": ("担保", "回测：凌钢披露亏损前约 11 个月，系统已提示这条担保关系", 1),
         "fangda_guarantee": ("担保", "反例：有关联担保但企业扛得住，系统没有误报", 2),
         "ansteel_related": ("关联交易", "最终盲测文档：一份关联交易公告抽出几十条交易记录", 3),
         "linggang_pledge": ("股权质押", "质押严重度按股东持股比例判断（10.91% 的股东质押，判为中）", 4),
         "fangda_maintenance": ("检修 · 网页", "新闻网页也能读：识别检修停产事件", 5)}
TASK_CN = {"guarantee": "担保", "related_party": "关联交易", "capacity": "检修 / 产能", "pledge": "股权质押"}


def pipeline_html() -> str:
    cells = "".join(
        f"<div style='flex:1 1 0;min-width:88px;border:1px solid var(--cp-line,#E4E7EC);border-radius:10px;padding:8px 8px 6px;background:#fff'>"
        f"<div style='font-size:11px;color:#98A2B3'>{i}</div><div style='font-weight:600;font-size:13px;color:#1D2433'>{name}</div>"
        f"<div style='font-size:11px;color:#667085;line-height:1.35;margin-top:2px'>{desc}</div></div>"
        + ("<div style='align-self:center;color:#98A2B3'>›</div>" if i < len(PIPELINE) else "")
        for i, (name, desc) in enumerate(PIPELINE, 1))
    return f"<div style='display:flex;gap:6px;flex-wrap:wrap;align-items:stretch'>{cells}</div>"


def model_configured() -> bool:
    return bool(os.environ.get("LLM_API_KEY", "").strip() and os.environ.get("LLM_MODEL", "").strip())


def check_model() -> tuple[bool, str]:
    """One tiny call to the configured model: (ok, message). Never prints the key."""
    if not model_configured():
        return False, "没有配置模型密钥或模型名称"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ.get("LLM_BASE_URL") or None, timeout=20)
        client.chat.completions.create(model=os.environ["LLM_MODEL"], messages=[{"role": "user", "content": "1"}], max_tokens=1)
        return True, f"模型可用（{os.environ['LLM_MODEL']}）"
    except Exception as error:                               # report the kind of failure, not the details
        text = str(error)
        if "model_not_found" in text or "Model not exist" in text:
            return False, f"模型名称不可用（{os.environ['LLM_MODEL']}）：服务商找不到这个模型"
        if "401" in text or "invalid_api_key" in text.lower():
            return False, "密钥无效或已过期"
        return False, f"连接失败（{type(error).__name__}）"


def recent_runs(days: int = 45) -> list[dict]:
    """Announcements the daily update downloaded in the last `days` days of runs, with the extraction status."""
    from datetime import date, timedelta
    files = sorted((ROOT / "data" / "manifests").glob("live_2*_sources.csv"))
    if not files:
        return []
    last = files[-1].stem.split("_")[1]
    start = (date(int(last[:4]), int(last[4:6]), int(last[6:])) - timedelta(days=days)).strftime("%Y%m%d")
    out = []
    for src in (f for f in files if f.stem.split("_")[1] >= start):
        split = src.stem.replace("_sources", "")
        log_path = ROOT / "outputs" / f"{split}_freeze" / "run_log.json"
        runs = json.loads(log_path.read_text(encoding="utf-8")).get("runs", {}) if log_path.exists() else {}
        with src.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                run = runs.get(r["file_name"], {})
                stem = Path(r["file_name"]).stem
                task = run.get("task") or ""
                doc = next((ROOT / "outputs" / f"{split}_freeze").glob(f"*/{stem}.json"), None)
                status = run.get("status") or "未运行"
                out.append({"日期": r["announcement_date"], "企业": r["security_name"], "公告": r["announcement_title"],
                            "类型": TASK_CN.get(task, task or "—"),
                            "抽取": {"success": "成功", "needs_review": "需人工复核", "failed": "失败"}.get(status, status),
                            "error": run.get("error", ""), "doc": str(doc) if doc else None, "url": r.get("source_url", ""),
                            "split": split})
    return sorted(out, key=lambda r: r["日期"], reverse=True)


def last_daily_failure(runs: list[dict]) -> str | None:
    failed = [r for r in runs if r["抽取"] == "失败"]
    if not failed:
        return None
    model = any("Model not exist" in r["error"] or "model_not_found" in r["error"] for r in failed)
    return (f"最近 {len(runs)} 份自动抓取的新公告中有 {len(failed)} 份抽取失败"
            + ("，原因是模型名称不可用（服务商找不到该模型）" if model else "") + "；这些公告目前只按标题识别信用事件。")
