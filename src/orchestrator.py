"""Dispatch agent (调度智能体): one announcement in, a traced decision out.

The agent does not chat; it runs a fixed plan and records, for every step, which tool it used, what went in,
what came out, what it decided and why - so the page can show the whole trajectory:

  ① 识别文档类型   rule tool   (detect_task on the title and first pages; the user can override)
  ② 选择工具       rule tool   (the frozen extractor + evidence validator for that type)
  ③ 结构化抽取     model tool  (frozen extraction system; or the saved output of that system, replayed)
  ④ 检查证据       rule tool   (every field checked against the page it claims to come from)
  ⑤ 实体解析       lookup      (both parties of every relation matched to a known company, or not)
  ⑥ 入图决策       rule tool   (auto into the graph only when ③-⑤ are clean; otherwise human review)
  ⑦ 承压查询       lookup      (fragility of the companies involved, point in time)
  ⑧ 计算敞口       calculation (guarantee amount / guarantor equity; trade volume is NOT exposure)
  ⑨ 传导推演       calculation (propagation from THIS document's signals)
  ⑩ 生成报告       template    (alert card with evidence)

The model is only used in ③ and was frozen before the tests; every decision after it is a written rule,
so the same input gives the same trajectory.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from src.analyze import TaskNotDetected, build_card, card_markdown, detect_task, offline_case
from src.entity_resolver import ROOT

TASK_LABEL = {"related_party": "日常关联交易", "guarantee": "对外担保", "capacity": "产能 / 检修", "pledge": "股权质押"}
TOOLS = {
    "related_party": ("关联交易抽取器（冻结版）", "RelatedPartyDocument", "关联交易证据校验器"),
    "guarantee": ("担保抽取器（冻结版）", "GuaranteeDocument", "担保证据校验器"),
    "capacity": ("产能 / 检修抽取器（冻结版）", "CapacityDocument", "产能证据校验器"),
    "pledge": ("股权质押抽取器（冻结版）", "PledgeDocument", "质押证据校验器"),
}
SCHEMA = {"related_party": ("schemas.related_party", "RelatedPartyDocument"), "guarantee": ("schemas.guarantee", "GuaranteeDocument"),
          "capacity": ("schemas.capacity", "CapacityDocument"), "pledge": ("schemas.pledge", "PledgeDocument")}
FREEZE_TAG = "extraction-freeze-2026-09-24"


class Trace:
    def __init__(self) -> None:
        self.steps: list[dict] = []

    def add(self, step: str, tool: str, kind: str, output: str, decision: str = "", reason: str = "",
            status: str = "ok", started: float | None = None, detail: list[str] | None = None) -> None:
        self.steps.append({"step": step, "tool": tool, "kind": kind, "output": output, "decision": decision,
                           "reason": reason, "status": status, "detail": detail or [],
                           "ms": round((time.perf_counter() - started) * 1000) if started else None})


def _pages(path: Path) -> list[dict]:
    from src.document_parser import parse_document
    parsed = parse_document(path)
    return [{"page": p.page, "text": p.text} for p in parsed.pages]


def _validate(task: str, doc: dict, pages: list[dict]) -> dict:
    import importlib

    from src.tasks import get_task
    module, cls = SCHEMA[task]
    model = getattr(importlib.import_module(module), cls).model_validate(doc)
    return get_task(task).validate(model, pages)


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def exposures(doc: dict, source: str, snapshot: str | None) -> list[dict]:
    """Y2 for this document: guarantees as a share of the guarantor's equity (an upper bound of the loss);
    related-party trade is shown as volume, explicitly not as exposure."""
    from src.chain_inputs import as_row, edges_from
    from src.entity_resolver import load_entities
    rows = [as_row(e) for e in edges_from(doc, source)[0]]
    equity = {r["security_code"]: float(r["equity"]) for r in _read(ROOT / "data" / "snapshots" / (snapshot or "-") / "quarterly_metrics.csv")
              if r.get("equity")}
    names = {k: v["short_name"] for k, v in load_entities()[0].items()}
    out: dict[tuple, dict] = {}
    for e in rows:
        if not e.get("amount_wan"):
            continue
        kind = "担保" if e["edge_type"] == "guarantee" else "交易额（非敞口）" if e["edge_type"] in ("supply", "service") else None
        if not kind:
            continue
        holder = e["src_id"] if e["edge_type"] == "guarantee" else e["issuer_id"]
        key = (kind, holder)
        r = out.setdefault(key, {"类型": kind, "承担方": names.get(holder, holder[2:] if holder.startswith("N_") else holder),
                                 "金额(亿元)": 0.0, "占承担方净资产": None, "条数": 0})
        r["金额(亿元)"] += float(e["amount_wan"]) / 1e4
        r["条数"] += 1
        if kind == "担保" and equity.get(holder):
            r["占承担方净资产"] = r["金额(亿元)"] * 1e8 / equity[holder]
    return [dict(r, **{"金额(亿元)": round(r["金额(亿元)"], 2)}) for r in out.values()]


def run(path: str | Path | None = None, case: dict | None = None, task: str | None = None, as_of: str | None = None,
        chain: str | Path | None = None, offline: bool = False) -> dict:
    """The traced plan. `case` = a demo-pack entry (replayed, no model call); otherwise `path` is analysed."""
    from datetime import date
    t = Trace()
    source_file = ROOT / case["source"] if case else Path(path)
    as_of = as_of or (case["as_of"] if case else date.today().isoformat())
    chain = Path(chain or (case["chain"] if case else "data/chain/live"))
    chain = chain if chain.is_absolute() else ROOT / chain
    case = case or offline_case(source_file)
    if offline and not case:
        raise TaskNotDetected("离线模式只能分析演示包里的文件（data/demo/）。请关闭离线模式，或选择演示包中的公告。")

    # ① document type
    s = time.perf_counter()
    try:
        pages = _pages(source_file)
    except Exception as error:  # noqa: BLE001 - e.g. no parser dependency; the plan continues without page checks
        pages = []
        t.add("① 识别文档类型", "文档解析", "规则", f"解析失败：{type(error).__name__}", status="warn", started=s)
    detected = detect_task("\n".join(p["text"] for p in pages[:2])) if pages else None
    replaying = bool(case) and (offline or not path)
    task = task or (case["task"] if replaying else None)      # a demo case knows its type; say whether the rule agrees
    chosen = task or detected
    if not chosen:
        t.add("① 识别文档类型", "关键词规则（标题优先，再看前两页）", "规则", "未识别", decision="停止，请用户选择类型",
              reason="标题和前两页没有关联交易、担保、产能/检修、质押的关键词；猜错类型会让错误的抽取器静默运行", status="stop", started=s)
        raise TaskNotDetected("无法从标题和前两页识别公告类型，请手动选择公告类型后重试。")
    who = "演示案例登记为" if replaying else "用户指定为"
    why = (f"{who}“{TASK_LABEL[chosen]}”" + (f"；规则识别为“{TASK_LABEL[detected]}”" if detected and detected != chosen else "；与规则识别一致" if detected else ""))\
        if task else f"标题或前两页命中“{TASK_LABEL[chosen]}”关键词"
    t.add("① 识别文档类型", "关键词规则（标题优先，再看前两页）", "规则", f"{TASK_LABEL[chosen]}（共 {len(pages)} 页）",
          decision=f"按“{TASK_LABEL[chosen]}”处理", reason=why, status="warn" if task and detected and detected != chosen else "ok", started=s)

    # ② tool choice
    extractor, schema, validator = TOOLS[chosen]
    t.add("② 选择工具", "工具路由", "规则", f"{extractor} + {validator}", decision=f"调用 {extractor}",
          reason=f"每类公告有独立的提示词、输出结构（{schema}）和证据校验器，均在 {FREEZE_TAG} 冻结，测试后未再修改")

    # ③ extraction
    s = time.perf_counter()
    result, status_word = None, "offline_replay"
    if replaying:
        doc = json.loads((ROOT / case["prediction"]).read_text(encoding="utf-8"))
        source = case["prediction_from"]
        t.add("③ 结构化抽取", f"回放：{extractor}此前对同一文件的输出", "大模型（冻结）", _count(doc),
              decision="不调用模型", reason=f"文件 SHA-256 与演示包一致，直接使用冻结系统的保存结果（{source}）", started=s)
    else:
        from src.pipeline import run_pipeline
        try:
            result = run_pipeline(source_file, task=chosen)
            doc = json.loads(Path(result["prediction_path"]).read_text(encoding="utf-8")) if result.get("prediction_path") else result["document"]
            source = str(Path(result["prediction_path"]).relative_to(ROOT)) if result.get("prediction_path") else str(source_file)
            status_word = result["status"]
            t.add("③ 结构化抽取", extractor, "大模型（冻结）", _count(doc), decision="抽取完成",
                  reason=f"模型调用 1 次，抽取状态 {status_word}", status="ok" if status_word == "success" else "warn", started=s)
        except Exception as error:
            if not case:
                t.add("③ 结构化抽取", extractor, "大模型（冻结）", f"失败：{type(error).__name__}", status="stop", started=s)
                raise
            doc = json.loads((ROOT / case["prediction"]).read_text(encoding="utf-8"))
            source = case["prediction_from"]
            t.add("③ 结构化抽取", extractor, "大模型（冻结）", _count(doc), decision="改用离线回放",
                  reason=f"模型调用失败（{type(error).__name__}），文件在演示包中，使用冻结系统的保存结果", status="warn", started=s)

    # ④ evidence
    s = time.perf_counter()
    report = (result or {}).get("evidence_report")
    if report is None and pages:
        try:
            report = _validate(chosen, doc, pages)
        except Exception as error:  # noqa: BLE001
            t.add("④ 检查证据", validator, "规则", f"未能校验：{type(error).__name__}", status="warn", started=s)
    if report is None and not pages:
        t.add("④ 检查证据", validator, "规则", "未取得原文页，无法逐项校验", decision="不能确认证据",
              reason="没有原文就不能证明数字出自原文；入图决策按“未通过”处理", status="warn", started=s)
    if report is not None:
        issues = report.get("issues") or []
        n = report.get("checks_count") or 0
        t.add("④ 检查证据", validator, "规则", f"{n - len(issues)}/{n} 项通过",
              decision="证据一致" if not issues else f"{len(issues)} 项需复核",
              reason="每个金额、主体、日期都要在它声称的那一页原文中找到", status="ok" if not issues else "warn", started=s,
              detail=[f"{i.get('field')}：{str(i.get('value'))[:30]}（{i.get('reason', '')}）" for i in issues[:5]])

    # ⑤ entities
    s = time.perf_counter()
    from src.chain_inputs import as_row, edges_from
    edges, skipped = edges_from(doc, source)
    edges = [as_row(e) for e in edges]
    unresolved = sorted({e[f"{side}_name"] for e in edges for side in ("src", "dst") if e.get(f"{side}_matched_by") == "unresolved"})
    t.add("⑤ 实体解析", "企业名称对照表（简称、全称、集团前缀）", "查询",
          f"{len(edges)} 条关系；{len(unresolved)} 个主体未匹配到已知企业；{skipped} 条因缺少主体名称被跳过",
          decision="主体齐全" if not skipped else "有缺失主体",
          reason="未匹配的主体作为新的非上市节点入图，不会被猜成已知企业", status="ok" if not skipped else "warn", started=s,
          detail=unresolved[:8])

    # ⑥ graph decision
    checks = [("抽取状态为 success" + ("（回放沿用冻结结果）" if result is None else ""),
               status_word == "offline_replay" if result is None else status_word == "success"),
              ("证据校验全部通过", report is not None and not (report.get("issues") or [])),
              ("所有关系的双方都有名称", skipped == 0)]
    auto = all(ok for _, ok in checks)
    t.add("⑥ 入图决策", "入图规则", "规则", "；".join(f"{'✓' if ok else '✗'} {name}" for name, ok in checks),
          decision="自动进入实时图谱" if auto else "转人工复核后再入图",
          reason="三项都满足才自动入图；任何一项不满足，结果照常展示，但不写入图谱，页面标“需人工复核”"
                 + ("（公开演示版和离线回放不写入图谱）" if case else ""), status="ok" if auto else "warn")

    # ⑦–⑨ fragility, exposure, propagation
    s = time.perf_counter()
    card = build_card(doc, source, as_of, chain)
    absorb = card["can_they_absorb"]
    t.add("⑦ 承压查询", f"承压评分快照 {card['snapshot']}", "查询",
          "；".join(f"{c['entity']} {c['tier']}" for c in absorb[:4]) or "涉及企业不在评分范围",
          reason="只用评估日当天已公开的数据", started=s)
    s = time.perf_counter()
    exp = exposures(doc, source, card["snapshot"])
    top = max((e for e in exp if e["占承担方净资产"] is not None), key=lambda e: e["占承担方净资产"], default=None)
    t.add("⑧ 计算敞口", "敞口 = 担保余额 ÷ 担保方净资产（损失上限）", "计算",
          "；".join([f"担保：{top['承担方']} {top['金额(亿元)']} 亿元，占其净资产 {top['占承担方净资产']:.1%}"] if top else
                    [f"担保：{e['承担方']} {e['金额(亿元)']} 亿元（无净资产数据）" for e in exp if e["类型"] == "担保"][:1]
                    + [f"交易额（非敞口）：{e['承担方']} {e['金额(亿元)']} 亿元" for e in exp if e["类型"] != "担保"][:1])
          or "本公告没有带金额的担保或交易",
          reason="担保是代偿上限；关联交易额是全年业务规模，不是可能的损失，单列为“交易额（非敞口）”", started=s)
    paths = card["who_is_next"]
    t.add("⑨ 传导推演", "传导规则 R1 担保 / R2 购销 / R3 同集团", "计算",
          f"{len(paths)} 条路径" + (f"；首条：{paths[0]['path']}（得分 {paths[0]['score']}）" if paths else ""),
          reason="只从本公告的信号出发；途经企业为强则吸收，金额低于对方净资产 1% 则停止")
    t.add("⑩ 生成报告", "预警卡片模板", "模板", "发生了什么 → 扛不扛得住 → 会传给谁，每条附原文页码")

    card.update({"task": chosen, "extraction_status": status_word, "chain": str(chain), "exposures": exp,
                 "trace": t.steps, "graph_decision": {"auto": auto, "checks": checks}})
    if case and result is None:
        card["offline_note"] = f"离线回放：未调用模型，使用冻结系统此前对同一文件（SHA-256 一致）的抽取结果（{case['prediction_from']}）。"
        card["doc_path"] = str(ROOT / case["prediction"])
    elif result is not None and result.get("prediction_path"):
        card["doc_path"] = str(result["prediction_path"])
    return card


def _count(doc: dict) -> str:
    for key, label in (("events", "条事件"), ("transactions", "条交易"), ("records", "条记录")):
        if isinstance(doc.get(key), list):
            return f"{len(doc[key])} {label}"
    return "已抽取"


def trace_markdown(card: dict) -> str:
    lines = ["## 调度轨迹"]
    for s in card.get("trace", []):
        lines.append(f"- {s['step']} · {s['tool']}（{s['kind']}）：{s['output']}"
                     + (f" → **{s['decision']}**" if s["decision"] else "") + (f"。理由：{s['reason']}" if s["reason"] else ""))
    return "\n".join(lines)


def full_markdown(card: dict) -> str:
    return card_markdown(card) + "\n\n" + trace_markdown(card)
