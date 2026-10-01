"""问一句：one question in, ONE existing tool called, a structured answer and its trace out.

The question is routed to a fixed menu of tools. Rules route first (company names, products, numbers, keywords);
only when the rules cannot place the question, and a model is configured, the model is asked to pick from the same
menu and its choice is validated. Every figure in the answer comes from the same deterministic functions the other
pages use (fragility snapshot, key paths, scenarios); the model never writes the answer. A question outside the menu
gets "not supported" and the list of what is.
"""
from __future__ import annotations

import csv
import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path

from src.entity_resolver import ROOT, load_entities
from src.orchestrator import Trace

CHAIN = ROOT / "data" / "chain" / "live"
INTENTS = {
    "company": ("企业风险概况", "这家企业自身扛不扛得住、有没有已发生的事件、和谁有风险关系"),
    "spread": ("会传给谁", "这家企业出问题时，风险会沿担保、关联交易、集团关系传给哪些上市公司"),
    "exposure": ("风险来自哪里", "哪些企业的风险会传到这家企业"),
    "today": ("今日预警", "当前的风险源和最值得关注的传导路径"),
    "ranking": ("承压排名", "核心钢厂中抗冲击能力最弱的企业"),
    "price": ("价格冲击情景", "某个产品价格大幅变动时，哪些企业暴露最大"),
    "export": ("出口政策冲击情景", "出口退税下调、关税或反倾销时，哪些钢厂暴露最大"),
    "document": ("分析新公告", "上传一份公告，抽取事实并推导影响"),
    "trust": ("系统可信度", "系统的结论经过了哪些检验、结果如何"),
}
EXAMPLES = ["安阳钢铁现在风险怎么样？", "八一钢铁出事会传给谁？", "哪些企业的风险会传到鞍钢股份？", "今天最该关注什么？",
            "承压最弱的钢厂有哪些？", "铁矿石涨 20% 谁受影响最大？", "出口关税提高 10% 对谁影响大？", "这个系统准不准？"]
NATURE = {"company": "模型预警 / 已发生事件", "spread": "情景假设", "exposure": "风险敞口 / 模型预警", "today": "已发生事件 / 风险敞口 / 模型预警",
          "ranking": "模型预警", "price": "情景假设", "export": "情景假设", "document": "", "trust": "已发生事件（检验结果）"}
KEYWORDS = [  # (intent, pattern) - first match wins; company-specific intents need a company
    ("document", r"公告|上传|这份|文件|pdf|PDF"),
    ("trust", r"准不准|准确|可信|靠谱|验证|检验|回测|证据等级"),
    ("export", r"出口|关税|反倾销|退税|海外|境外"),
    ("spread", r"传给|传到谁|传导到哪|影响谁|影响哪些|波及|连累|拖累|殃及|出事.*谁|出问题.*谁|暴雷.*谁"),
    ("exposure", r"传到|来自|被.*影响|受.*影响|谁会影响|风险来源|哪些企业的风险|上游.*风险|被谁"),
    ("ranking", r"最弱|最差|最危险|风险最大|排名|排行|哪些.*(弱|危险)|前几|前十"),
    ("today", r"今天|今日|当前|现在|最近|最该|关注什么|预警"),
]
MOVE = re.compile(r"(涨|上涨|上升|提高|增加|跌|下跌|下降|降低|减少|下调|上调)?\s*(\d+(?:\.\d+)?)\s*(%|％|个百分点|成)")
DOWN = re.compile(r"跌|下跌|下降|降低|减少|下调")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def name_index() -> list[tuple[str, str, str]]:
    """(name as it may appear in a question, security code, display name), longest names first."""
    out = {}
    companies = _read(ROOT / "data" / "manifests" / "steel_universe.csv")
    companies += [r for r in _read(ROOT / "data" / "manifests" / "extension_universe.csv")]
    for r in companies:
        code, name = r["security_code"], r["security_name"]
        for key in {name, code, re.sub(r"股份$|集团$", "", name)}:
            if len(key) >= 2:
                out.setdefault(key, (code, name))
    rows, _ = load_entities()
    for r in rows.values():
        code = r.get("security_code")
        if code:
            display = next((v[1] for v in out.values() if v[0] == code), r["short_name"])
            for key in [r["short_name"], r["canonical_name"]] + [a for a in r["aliases"].split("|") if a]:
                if len(key) >= 2:
                    out.setdefault(key, (code, display))
    return sorted(((k, c, n) for k, (c, n) in out.items()), key=lambda t: -len(t[0]))


def find_companies(text: str) -> list[tuple[str, str]]:
    found, taken = [], []
    for key, code, name in name_index():
        start = text.find(key)
        if start < 0 or any(a <= start < b for a, b in taken) or code in (c for c, _ in found):
            continue
        taken.append((start, start + len(key)))
        found.append((code, name))
    return found


@lru_cache(maxsize=1)
def _products() -> list[dict]:
    from src.product_layer import products
    return products()


def find_product(text: str) -> tuple[str, str] | None:
    for p in _products():
        if p["name"] in text or any(k and k in text for k in p["keywords"].split("|")):
            return p["product_id"], p["name"]
    return None


def find_move(text: str) -> float | None:
    m = MOVE.search(text)
    if not m:
        return None
    value = float(m.group(2)) / (10 if m.group(3) == "成" else 100)
    return -value if DOWN.search(m.group(1) or "") or (not m.group(1) and DOWN.search(text)) else value


def rule_route(question: str) -> dict:
    q = question.strip()
    companies = find_companies(q)
    product = find_product(q)
    move = find_move(q)
    intent = None
    for name, pattern in KEYWORDS:
        if re.search(pattern, q):
            if name in ("spread", "exposure") and not companies:
                continue
            if name == "today" and companies:
                continue
            intent = name
            break
    if intent is None and product and (move is not None or re.search(r"涨|跌|价格|价", q)):
        intent = "price"
    if intent in (None, "today") and product and move is not None:
        intent = "price"
    if intent is None and companies:
        intent = "company"
    return {"intent": intent or "unsupported", "companies": companies, "product": product, "move": move, "by": "规则"}


def model_available() -> bool:
    return bool(os.environ.get("LLM_API_KEY", "").strip() and os.environ.get("LLM_MODEL", "").strip())


def model_route(question: str) -> dict | None:
    """Ask the model to pick ONE tool from the menu. Its answer is validated; anything else is ignored."""
    from openai import OpenAI
    menu = "\n".join(f"- {k}: {v[0]}——{v[1]}" for k, v in INTENTS.items())
    prompt = ("你是一个问题分类器，只能从下面的工具中选一个，或回答 unsupported。不要回答问题本身。\n"
              f"{menu}\n- unsupported: 以上都不适用\n"
              '只输出 JSON：{"intent": "...", "company": "问题中提到的公司名或空字符串", "product": "问题中的产品或空字符串", '
              '"change": 价格或税率变动的小数（如上涨20%为0.2，下降为负数），没有就为 null}')
    client = OpenAI(api_key=os.environ["LLM_API_KEY"], base_url=os.environ.get("LLM_BASE_URL") or None, timeout=20)
    reply = client.chat.completions.create(model=os.environ["LLM_MODEL"], temperature=0,
                                           response_format={"type": "json_object"},
                                           messages=[{"role": "system", "content": prompt}, {"role": "user", "content": question}])
    data = json.loads(reply.choices[0].message.content or "{}")
    intent = data.get("intent") if data.get("intent") in INTENTS else "unsupported"
    companies = find_companies(str(data.get("company") or "")) or find_companies(question)
    product = find_product(str(data.get("product") or "")) or find_product(question)
    move = data.get("change") if isinstance(data.get("change"), (int, float)) else find_move(question)
    if intent in ("company", "spread", "exposure") and not companies:
        intent = "unsupported"
    return {"intent": intent, "companies": companies, "product": product, "move": move,
            "by": f"模型（{os.environ['LLM_MODEL']}，只做分类）"}


# ---------- data (cached: the same snapshot and live graph as the other pages) ----------

def latest_snapshot() -> Path:
    from src.profile import snapshots
    return ROOT / "data" / "snapshots" / snapshots()[0]


@lru_cache(maxsize=4)
def _paths(chain: str, snapshot: str):
    from src.network_view import key_paths
    return key_paths(Path(chain), Path(snapshot))


def _fragility(snapshot: Path) -> dict[str, dict]:
    from src.profile import fragility_rows
    return {r["security_code"]: r for r in fragility_rows(snapshot.name)}


def _path_table(items: list[tuple[int, dict]], names: dict, snapshot: Path, limit: int = 8) -> list[dict]:
    from src.network_view import path_rows, snapshot_equity
    return path_rows(items[:limit], names, None, snapshot_equity(snapshot))


TIER_CN = {"weak": "弱", "medium": "中", "strong": "强"}


def _tier_text(row: dict | None) -> str:
    if not row or not row.get("tier"):
        return "未评分"
    return f"{TIER_CN.get(row['tier'], row['tier'])}（{row.get('total_score', '—')} 分，满分 100，越高越弱）"


# ---------- answers ----------

def answer_company(code: str, name: str, snapshot: Path, trace: Trace) -> dict:
    from src.live_events import active
    from src.network_view import coverage
    t = time.perf_counter()
    f = _fragility(snapshot).get(code)
    events = [e for e in active(snapshot.name) if e["security_code"] == code]
    ranked, _, names = _paths(str(CHAIN), str(snapshot))
    out = [(i, e) for i, e in enumerate(ranked) if e["seed"] == code and e["score"] > 0]
    inc = [(i, e) for i, e in enumerate(ranked) if e["seed"] != code and e["score"] > 0
           and any(s.dst == code for s in e["steps"])]
    cov = coverage(CHAIN, snapshot, code)
    trace.add("④ 调用工具", "承压快照 + 信用事件表 + 实时图谱关键路径", "lookup",
              f"承压 {_tier_text(f)}；生效事件 {len(events)} 条；以它为起点 {len(out)} 条、传入 {len(inc)} 条；生效披露关系 {len(cov['active'])} 条",
              started=t)
    level = "error" if events or (f or {}).get("tier") == "weak" else "warning" if (f or {}).get("tier") == "medium" else "success"
    text = f"{name}：抗冲击能力{_tier_text(f)}"
    text += f"；12 个月内已发生 {len(events)} 起信用事件" if events else "；近 12 个月没有识别到已发生的信用事件"
    text += f"；风险会传出 {len(out)} 条、传入 {len(inc)} 条关键路径。"
    tables = []
    if f:
        tables.append(("承压评分（模型预警）", [{"总分": f.get("total_score"), "档位": TIER_CN.get(f.get("tier"), ""),
                                          "红线与极差": f.get("red_lines") or "无", "财报期": f.get("period", ""),
                                          "同组": f.get("peer_group", "")}]))
    if events:
        tables.append(("已发生的信用事件（事实）", [{"日期": e["date"], "事件": e["event_label"], "公告标题": e["title"],
                                             "核对状态": e["status"]} for e in events]))
    if out:
        tables.append(("它的风险会传给谁", _path_table(out, names, snapshot)))
    if inc:
        tables.append(("谁的风险会传到它", _path_table(inc, names, snapshot)))
    note = "" if out or inc else (f"没有关键路径：当前生效的披露关系 {len(cov['active'])} 条，已过期 {len(cov['expired'])} 条，"
                                  f"最近一份相关公告 {cov['latest'] or '无'}。")
    return {"verdict": (level, text), "tables": tables, "note": note, "goto": ("pages/7_企业档案.py", "打开企业档案", code)}


def answer_spread(code: str, name: str, snapshot: Path, trace: Trace) -> dict:
    from src.network_view import second_order
    t = time.perf_counter()
    ranked, _, names = _paths(str(CHAIN), str(snapshot))
    actual = [(i, e) for i, e in enumerate(ranked) if e["seed"] == code and e["score"] > 0]
    hypo = second_order(CHAIN, snapshot, [code]).get(code, [])
    trace.add("④ 调用工具", "实时图谱关键路径 + 假设情景推演（second_order，假设严重度：中）", "calculation",
              f"现有风险源路径 {len(actual)} 条；假设它出事时的路径 {len(hypo)} 条", started=t)
    tables = []
    if actual:
        tables.append(("它本身已是风险源：当前的传导路径", _path_table(actual, names, snapshot)))
    if hypo:
        tables.append(("情景：假设它出现中等严重的信用问题", _path_table(list(enumerate(hypo)), names, snapshot)))
    reached = sorted({names.get(s.dst, s.dst) for e in hypo for s in e["steps"]})
    text = (f"如果{name}出问题，按公告披露的关系，风险可能传到：{'、'.join(reached[:8])}" + ("等" if len(reached) > 8 else "") + "。"
            if reached else f"按当前生效的披露关系，{name}出问题时没有可推导的、经过其他上市公司的传导路径。")
    return {"verdict": ("warning" if reached else "info", text), "tables": tables,
            "note": "情景假设：不是预测它会出事，而是回答“如果它出事”。", "goto": ("pages/8_风险传导总图.py", "在风险传导图上查看", code)}


def answer_exposure(code: str, name: str, snapshot: Path, trace: Trace) -> dict:
    t = time.perf_counter()
    ranked, _, names = _paths(str(CHAIN), str(snapshot))
    inc = [(i, e) for i, e in enumerate(ranked) if e["seed"] != code and e["score"] > 0 and any(s.dst == code for s in e["steps"])]
    trace.add("④ 调用工具", "实时图谱关键路径（终点或途经该企业）", "lookup", f"传入路径 {len(inc)} 条", started=t)
    sources = sorted({names.get(e["seed"], e["seed"]) for _, e in inc})
    text = (f"有 {len(inc)} 条关键路径会把风险传到{name}，起点包括：{'、'.join(sources[:8])}。" if inc
            else f"当前没有其他企业的风险沿披露关系传到{name}。")
    return {"verdict": ("warning" if inc else "success", text), "tables": [("传入路径", _path_table(inc, names, snapshot))] if inc else [],
            "note": "", "goto": ("pages/7_企业档案.py", "打开企业档案", code)}


def answer_today(snapshot: Path, trace: Trace) -> dict:
    from src.network_view import risk_sources
    t = time.perf_counter()
    sources = risk_sources(CHAIN, snapshot)
    ranked, _, names = _paths(str(CHAIN), str(snapshot))
    top = [(i, e) for i, e in enumerate(ranked) if e["score"] > 0][:5]
    trace.add("④ 调用工具", "风险源列表 + 关键路径排名", "lookup", f"风险源 {len(sources)} 个；展示前 5 条路径", started=t)
    facts = [s for s in sources if s["nature"] == "已发生事件"]
    text = f"截至 {snapshot.name}：已发生事件 {len(facts)} 个、风险源合计 {len(sources)} 个。"
    if top:
        text += f"最值得关注的路径：{_path_table(top[:1], names, snapshot)[0]['传导路径']}。"
    rows = [{"性质": s["nature"], "风险源": s["name"], "类型": s["kind_label"], "严重度": s["severity"], "说明": s["reason"][:60],
             "会波及": "、".join(s["reached"][:4])} for s in sources[:10]]
    return {"verdict": ("warning", text), "tables": [("风险源（按性质排序）", rows), ("关键传导路径 Top 5", _path_table(top, names, snapshot))],
            "note": "", "goto": ("pages/0_今日看板.py", "打开今日预警", None)}


def answer_ranking(snapshot: Path, trace: Trace) -> dict:
    t = time.perf_counter()
    core = [r for r in _fragility(snapshot).values() if r.get("peer_group") == "core" and r.get("total_score")]
    order = sorted(core, key=lambda r: -float(r["total_score"]))
    trace.add("④ 调用工具", "承压快照（24 家核心钢厂）", "lookup", f"{len(order)} 家，按总分排序", started=t)
    weak = [r["security_name"] for r in order if r.get("tier") == "weak"]
    rows = [{"排名": i, "企业": r["security_name"], "总分": r["total_score"], "档位": TIER_CN.get(r.get("tier"), ""),
             "红线与极差": (r.get("red_lines") or "")[:50]} for i, r in enumerate(order[:10], 1)]
    return {"verdict": ("warning", f"核心钢厂中抗冲击能力为“弱”的有 {len(weak)} 家：{'、'.join(weak)}。"),
            "tables": [("承压最弱的 10 家（模型预警，不是违约预测）", rows)], "note": "", "goto": ("pages/2_承压评分.py", "打开承压评分全表", None)}


def answer_price(product: tuple[str, str], move: float | None, snapshot: Path, trace: Trace) -> dict:
    from src.price_shock import CAVEAT, exposed, scenario_stress
    t = time.perf_counter()
    move = -0.2 if move is None else move
    rows = scenario_stress(exposed(product[0], snapshot.name, _fragility(snapshot), top=10), move)
    trace.add("④ 调用工具", "产品暴露（东方财富主营构成，B 级）× 承压档位", "calculation",
              f"{product[1]} 变动 {move:+.0%}：{len(rows)} 家企业有该产品收入", started=t)
    table = [{"企业": r["name"], "该产品收入占比": f"{r['share']:.0%}", "承压": r["tier_label"], "情景指数": r["stress_index"],
              "数据期": r["period"]} for r in rows]
    text = (f"{product[1]}价格变动 {move:+.0%} 时，暴露最大的是 {table[0]['企业']}（该产品收入占 {table[0]['该产品收入占比']}）。"
            if table else f"没有企业披露 {product[1]} 收入占比在 10% 以上。")
    note = CAVEAT
    if product[0] in ("P_IRON_ORE", "P_COKING_COAL", "P_COKE"):
        note += " 对钢厂来说这是采购成本：钢厂不披露采购占比，这里只列出卖这个产品的企业；铁矿石外购比例的冲击检验未达显著（docs/shock_transmission_preregistration.md）。"
    return {"verdict": ("info", text), "tables": [(f"{product[1]}价格冲击情景", table)] if table else [], "note": note,
            "goto": ("pages/5_上下游情景.py", "打开供需情景与政策冲击", None)}


def answer_export(move: float | None, snapshot: Path, trace: Trace) -> dict:
    from src.policy_shock import export_change
    t = time.perf_counter()
    change = abs(move) if move is not None else 0.05
    rows = [r for r in export_change(_fragility(snapshot), snapshot.name, change) if r["index"] is not None][:10]
    trace.add("④ 调用工具", "境外收入占比（年报 A 级 / 东方财富 B 级）× 承压档位", "calculation",
              f"冲击幅度 {change:.0%}：{len(rows)} 家有境外收入数据", started=t)
    table = [{"企业": r["name"], "境外收入占比": f"{r['overseas_share']:.1%}", "承压": TIER_CN.get(r["tier"], ""),
              "情景指数": r["index"], "来源": r["overseas_source"]} for r in rows]
    text = f"出口成本上升 {change:.0%} 时，暴露最大的是 {table[0]['企业']}（境外收入占 {table[0]['境外收入占比']}）。" if table else "没有境外收入数据。"
    return {"verdict": ("info", text), "tables": [("出口政策冲击情景", table)] if table else [],
            "note": "情景假设：暴露程度不是损失预测；境外收入占比对汇率冲击的预登记检验未通过（docs/shock_transmission_preregistration.md）。",
            "goto": ("pages/5_上下游情景.py", "打开供需情景与政策冲击", None)}


def answer_trust(trace: Trace) -> dict:
    t = time.perf_counter()
    rows = [
        {"检验": "承压评分能否区分谁更容易出事（预注册）", "结果": "弱组 22/49（44.9%）vs 非弱组 15/119（12.6%），p < 0.0001", "判定": "通过"},
        {"检验": "与简单指标比较（事后）", "结果": "最近季报净利率的 AUC 0.903，高于承压评分 0.754", "判定": "评分不优于单一盈利指标"},
        {"检验": "产品暴露能否解释利润与股价分化（预登记两次）", "结果": "方向一致但未显著", "判定": "未通过"},
        {"检验": "铁矿石冲击 × 外购比例（预登记）", "结果": "平均 z = 0.024，p = 0.29", "判定": "方向一致但未显著"},
        {"检验": "汇率冲击 × 境外收入占比（预登记）", "结果": "平均 z = −0.059，p = 0.90", "判定": "未通过"},
    ]
    trace.add("④ 调用工具", "验证结果汇总（docs/ 下的预登记与结果文件）", "lookup", f"{len(rows)} 项检验", started=t)
    return {"verdict": ("info", "每个结论都标明性质（事实 / 敞口 / 模型预警 / 情景），检验先登记后运行，通过和未通过的都如实列出。"),
            "tables": [("主要检验结果", rows)], "note": "", "goto": ("pages/6_验证与证据.py", "打开可信度页", None)}


def ask(question: str, use_model: bool = True, snapshot: Path | None = None) -> dict:
    trace = Trace()
    t = time.perf_counter()
    route = rule_route(question)
    trace.add("① 理解问题", "规则路由（公司名、产品、数字、关键词）", "rule",
              f"意图：{INTENTS.get(route['intent'], ('不支持',))[0]}", started=t)
    if route["intent"] == "unsupported" and use_model and model_available():
        t = time.perf_counter()
        try:
            got = model_route(question)
            route = got or route
            trace.add("① 理解问题（补充）", "模型分类（只能在固定工具中选择）", "model",
                      f"意图：{INTENTS.get(route['intent'], ('不支持',))[0]}", started=t)
        except Exception as error:  # noqa: BLE001
            trace.add("① 理解问题（补充）", "模型分类", "model", f"失败：{type(error).__name__}", status="error", started=t)
    trace.add("② 识别对象", "名称表（42 家 + 扩展组）、产品表、数字", "lookup",
              "；".join(filter(None, [("企业：" + "、".join(n for _, n in route["companies"])) if route["companies"] else "",
                                       f"产品：{route['product'][1]}" if route["product"] else "",
                                       f"幅度：{route['move']:+.0%}" if route["move"] is not None else ""])) or "无")
    intent = route["intent"]
    snapshot = snapshot or latest_snapshot()
    trace.add("③ 选择工具", "固定工具菜单", "rule", INTENTS[intent][0] if intent in INTENTS else "不支持：不调用任何工具",
              reason=INTENTS[intent][1] if intent in INTENTS else "")
    code, name = route["companies"][0] if route["companies"] else (None, None)
    if intent == "company":
        result = answer_company(code, name, snapshot, trace)
    elif intent == "spread":
        result = answer_spread(code, name, snapshot, trace)
    elif intent == "exposure":
        result = answer_exposure(code, name, snapshot, trace)
    elif intent == "today":
        result = answer_today(snapshot, trace)
    elif intent == "ranking":
        result = answer_ranking(snapshot, trace)
    elif intent == "price" and route["product"]:
        result = answer_price(route["product"], route["move"], snapshot, trace)
    elif intent == "export":
        result = answer_export(route["move"], snapshot, trace)
    elif intent == "trust":
        result = answer_trust(trace)
    elif intent == "document":
        result = {"verdict": ("info", "请到“分析新公告”上传 PDF 或选择演示案例：调度智能体会抽取事实、核对证据并推导影响。"),
                  "tables": [], "note": "", "goto": ("pages/3_一键分析.py", "打开分析新公告", None)}
    else:
        intent = "unsupported"
        result = {"verdict": ("info", "这个问题不在系统能回答的范围内。系统只回答下面几类问题，所有答案都来自公告与财务数据："),
                  "tables": [("能回答的问题", [{"类型": v[0], "说明": v[1]} for v in INTENTS.values()])], "note": "", "goto": None}
    trace.add("⑤ 生成回答", "模板（结论一句 + 表格 + 性质标注）", "template", f"{len(result['tables'])} 张表")
    return {"question": question, "intent": intent, "label": INTENTS.get(intent, ("不支持",))[0], "nature": NATURE.get(intent, ""),
            "route": {**route, "companies": [n for _, n in route["companies"]],
                      "product": route["product"][1] if route["product"] else None},
            "snapshot": snapshot.name, "trace": trace.steps, **result}
