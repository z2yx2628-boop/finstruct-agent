"""Command bar (Bloomberg-style "<security> <function>"): parse a typed line into a destination.

    凌钢 / 600231 / LGGF          -> company profile (DES)
    凌钢 FA / 凌钢财报            -> profile, 财报分析 section
    安泰 RELS / 安泰 传导         -> risk-transmission map starting from 安泰集团
    期货 / CMDTY                 -> futures scenario page;  凌钢 期货 -> profile, 产品与价格 section
    ?凌钢会传给谁 / 一句完整的问题  -> 问一句

Pure functions only (no Streamlit) so the parser can be tested; src/ui.py renders the bar.
Function codes borrow Bloomberg's names where one exists (DES, DRSK, FA, RELS, SPLC, CN).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# code -> (Chinese label, target, profile section)
FUNCS = {
    "DES": ("档案", "profile", "自身风险"),
    "DRSK": ("承压评分", "profile", "自身风险"),
    "FA": ("财报分析", "profile", "财报分析"),
    "RELS": ("风险传导", "unified", None),
    "LINK": ("关联风险", "profile", "关联风险"),
    "SPLC": ("客户与供应商", "profile", "客户与供应商"),
    "CMDTY": ("期货与原料", "profile", "产品与价格"),
    "PROD": ("产品暴露", "profile", "产品与价格"),
    "CN": ("公告信号", "profile", "公告信号"),
    "BRIEF": ("核查底稿", "profile", "自身风险"),
}
WORDS = {  # Chinese keyword -> function code (longest first when matching)
    "档案": "DES", "概况": "DES", "评分": "DRSK", "承压": "DRSK", "脆弱": "DRSK", "财报": "FA", "财务": "FA",
    "传导": "RELS", "路径": "RELS", "传导图": "RELS", "关联": "LINK", "担保": "LINK", "客户": "SPLC", "供应商": "SPLC",
    "供应链": "SPLC", "上下游": "SPLC", "期货": "CMDTY", "原料": "CMDTY", "套保": "CMDTY", "铁矿": "CMDTY",
    "产品": "PROD", "螺纹": "CMDTY", "热卷": "CMDTY", "焦炭": "CMDTY", "焦煤": "CMDTY", "盘面": "CMDTY", "公告": "CN", "底稿": "BRIEF", "简报": "BRIEF", "报告": "BRIEF",
}
PAGES = {  # page commands that need no company
    "首页": "views/0_今日看板.py", "预警": "views/0_今日看板.py", "今日": "views/0_今日看板.py",
    "可信度": "views/6_验证与证据.py", "验证": "views/6_验证与证据.py", "检验": "views/6_验证与证据.py",
    "新公告": "views/3_一键分析.py", "分析公告": "views/3_一键分析.py", "评分表": "views/2_承压评分.py",
    "情景": "views/5_上下游情景.py", "政策": "views/5_上下游情景.py", "传导图": "views/8_风险传导总图.py",
}
QUESTION = re.compile(r"[?？]|吗|谁|什么|怎么|哪些|哪家|为什么|如何|会不会|多少|是否")


def load_companies(fragility_rows: list[dict]) -> list[dict]:
    """Searchable companies: the scored companies (core first, weakest first) plus pinyin initials."""
    aliases = {}
    path = ROOT / "data" / "reference" / "search_aliases.csv"
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            aliases = {r["security_code"]: r for r in csv.DictReader(f)}
    rows = sorted(fragility_rows, key=lambda r: (r.get("peer_group") != "core", -float(r.get("total_score") or 0)))
    out, seen = [], set()
    for r in rows:
        code = r["security_code"]
        if code in seen:
            continue
        seen.add(code)
        a = aliases.get(code, {})
        out.append({"code": code, "name": r["security_name"], "initials": a.get("initials", ""),
                    "nicknames": [n for n in (a.get("nicknames") or "").split(";") if n],
                    "tier": r.get("tier", ""), "score": r.get("total_score", "")})
    return out


def find_companies(text: str, companies: list[dict]) -> list[dict]:
    t = text.strip().upper()
    hits = []
    for c in companies:
        name = c["name"].replace("*", "")
        if c["code"] in t or (len(name) >= 2 and name in text) or any(n in text for n in c.get("nicknames", [])):
            hits.append((0, c))
        elif any(len(tok) >= 2 and (name.startswith(tok) or tok in name) for tok in re.findall(r"[一-鿿]{2,}", text)) \
                or (len(name) >= 3 and name[:2] in text):
            hits.append((1, c))
        elif c["initials"] and any(tok == c["initials"] for tok in re.findall(r"[A-Z]{2,}", t)):
            hits.append((2, c))
    best = min((h[0] for h in hits), default=None)
    return [c for rank, c in hits if rank == best]


def find_function(text: str) -> str | None:
    up = text.upper()
    for code in sorted(FUNCS, key=len, reverse=True):
        if re.search(rf"(?<![A-Z]){code}(?![A-Z])", up):
            return code
    for word in sorted(WORDS, key=len, reverse=True):
        if word in text:
            return WORDS[word]
    return None


def parse(text: str, companies: list[dict]) -> dict:
    """-> {"kind": "company" | "page" | "ask" | "none", ...}."""
    text = (text or "").strip()
    if not text:
        return {"kind": "none"}
    if text[0] in "?？":
        return {"kind": "ask", "question": text[1:].strip()}
    picked = re.match(r"^(\d{6})\b", text)                    # a suggestion picked from the list starts with its code
    hits = [c for c in companies if picked and c["code"] == picked.group(1)] or find_companies(text, companies)
    func = find_function(text)
    if QUESTION.search(text) and len(text) >= 6:
        return {"kind": "ask", "question": text}
    if hits:
        code = func or "DES"
        label, target, section = FUNCS[code]
        return {"kind": "company", "company": hits[0], "others": hits[1:], "func": code, "label": label,
                "target": target, "section": section}
    if func == "CMDTY":
        return {"kind": "page", "page": "views/5_上下游情景.py", "state": {"sc_source": "期货与套保"}, "label": "期货情景与套保"}
    for word, page in sorted(PAGES.items(), key=lambda kv: -len(kv[0])):
        if word in text:
            return {"kind": "page", "page": page, "state": {}, "label": word}
    if len(text) >= 6:
        return {"kind": "ask", "question": text}
    return {"kind": "none", "text": text}


def suggestion(c: dict) -> str:
    tier = {"weak": "🔴 弱", "medium": "🟡 中", "strong": "🟢 强"}.get(c["tier"], "")
    return f"{c['code']} {c['name']}" + (f" · {tier} {c['score']} 分" if tier else "")
