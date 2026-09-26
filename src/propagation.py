"""Direction 3: rule-based risk propagation over the evidence graph (white box).

Seeds: risk signals from direction 1 and companies rated weak by direction 2.
Rules (docs/propagation_rules.md):
  R1 guarantee : guaranteed party in trouble -> guarantor (must pay)            [credit]
  R2 supply    : supplier disrupted -> buyer (supply)  ; buyer weak -> supplier (receivables) [supply/credit]
  R3 group     : trouble inside a group -> the group's other listed members     [credit]
  R4 industry  : supply disruption -> own industry -> downstream industry -> its weak members only (one hop)
Every step decides with the next company's fragility tier (as of the same date):
  weak -> continue at the same severity; medium/unknown -> continue one level lower; strong -> absorbed, stop.
A step whose amount is below MATERIALITY of the next company's equity stops. Paths have at most MAX_HOPS steps.
Each step carries its evidence: source document, page and sentence, or "industry_approx" for R4.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

MAX_HOPS = 3
MATERIALITY = 0.01
LEVELS = ["low", "medium", "high"]
SUPPLY_SIGNALS = {"supply_disruption", "capacity_reduction"}
CREDIT_SIGNALS = {"credit_event", "credit_exposure", "share_pledge"}
TRADE = {"supply", "service", "lease"}


@dataclass
class Step:
    rule: str
    src: str
    dst: str
    shock: str
    severity: str
    dst_tier: str
    decision: str            # continue | weakened | absorbed | immaterial | end
    basis: str
    evidence: str
    note: str = ""


@dataclass
class Path:
    seed: str
    seed_reason: str
    steps: list[Step] = field(default_factory=list)


def lower(level: str) -> str | None:
    i = LEVELS.index(level)
    return LEVELS[i - 1] if i > 0 else None


class Graph:
    def __init__(self, edges: list[dict], fragility: dict[str, dict], equity: dict[str, float],
                 groups: dict[str, str], listed: set[str]):
        self.fragility, self.equity, self.groups, self.listed = fragility, equity, groups, listed
        self.out = defaultdict(list)          # (node, shock) -> [(next, rule, edge)]
        self.members = defaultdict(set)       # industry -> companies
        self.industry_of = {}
        industry_next = defaultdict(list)
        for e in edges:
            t, s, d = e["edge_type"], e["src_id"], e["dst_id"]
            if t == "guarantee":
                self.out[(d, "credit")].append((s, "R1", e))
            elif t in TRADE:
                self.out[(s, "supply")].append((d, "R2", e))
                self.out[(d, "credit")].append((s, "R2", e))
            elif t == "member_of":
                self.members[d].add(s)
                self.industry_of[s] = d
            elif t == "industry":
                industry_next[s].append((d, e))
        self.industry_next = industry_next

    def tier(self, node: str) -> str:
        return self.fragility.get(node, {}).get("tier") or "unknown"

    def material(self, edge: dict, node: str) -> bool:
        amount = edge.get("amount_wan")
        equity = self.equity.get(node)
        if amount in (None, "") or not equity or equity <= 0:
            return True                          # cannot judge: do not stop on missing data
        return float(amount) * 1e4 / equity >= MATERIALITY

    def next_steps(self, node: str, shock: str) -> list[tuple[str, str, dict]]:
        steps = merge_parallel(self.out.get((node, shock), []))
        group = self.groups.get(node)
        if shock == "credit" and group:
            for other, g in self.groups.items():
                if g == group and other != node and other in self.listed:
                    steps.append((other, "R3", {"basis": "entity_table", "evidence_text": f"同属集团 {group}",
                                                "source_doc": "data/reference/entities.csv"}))
        if shock == "supply" and node in self.industry_of:
            for downstream, e in self.industry_next.get(self.industry_of[node], []):
                for member in sorted(self.members.get(downstream, ())):
                    if self.tier(member) == "weak":
                        steps.append((member, "R4", e))
        return steps


def merge_parallel(options: list[tuple[str, str, dict]]) -> list[tuple[str, str, dict]]:
    """Several table rows between the same two companies are one relationship: sum the
    amounts and keep the largest row as the evidence shown."""
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for nxt, rule, edge in options:
        grouped[(nxt, rule)].append(edge)
    merged = []
    for (nxt, rule), edges in grouped.items():
        amounts = [float(e["amount_wan"]) for e in edges if e.get("amount_wan") not in (None, "")]
        top = max(edges, key=lambda e: float(e["amount_wan"]) if e.get("amount_wan") not in (None, "") else -1)
        edge = dict(top)
        edge["amount_wan"] = sum(amounts) if amounts else None
        if len(edges) > 1:
            edge["evidence_text"] = f"（共{len(edges)}行，合计{edge['amount_wan'] or '-'}万元；最大一行）" + (top.get("evidence_text") or "")
        merged.append((nxt, rule, edge))
    return merged


def evidence_of(edge: dict) -> str:
    page = edge.get("source_page")
    where = f"{edge.get('source_doc', '')}" + (f" 第{page}页" if page not in (None, "") else "")
    return f"{where}：{(edge.get('evidence_text') or edge.get('category_text') or '')[:80]}"


def propagate(graph: Graph, seed: str, shock: str, severity: str, reason: str) -> list[Path]:
    """Depth-first expansion; one Path per branch that reaches an end."""
    finished: list[Path] = []

    def walk(node: str, level: str, path: Path, visited: set[str]) -> None:
        used_group = any(s.rule == "R3" for s in path.steps)   # group spread at most once per path
        options = [o for o in graph.next_steps(node, shock)
                   if o[0] not in visited and not (o[1] == "R3" and used_group)]
        if not options or len(path.steps) >= MAX_HOPS:
            if path.steps:
                finished.append(path)
            return
        for nxt, rule, edge in options:
            tier = graph.tier(nxt)
            step = Step(rule, node, nxt, shock, level, tier, "continue", edge.get("basis", "disclosed"),
                        evidence_of(edge))
            branch = Path(path.seed, path.seed_reason, path.steps + [step])
            if rule != "R4" and not graph.material(edge, nxt):
                step.decision, step.note = "immaterial", f"金额低于对方净资产的{MATERIALITY:.0%}"
                finished.append(branch)
                continue
            if tier == "strong":
                step.decision, step.note = "absorbed", "承压评分为强，风险在此被吸收"
                finished.append(branch)
                continue
            next_level = level if tier == "weak" else lower(level)
            if next_level is None:
                step.decision, step.note = "end", "严重程度已降至最低"
                finished.append(branch)
                continue
            if tier != "weak":
                step.decision = "weakened"
            if rule == "R4":                       # industry links: one hop only, never chained
                finished.append(branch)
                continue
            walk(nxt, next_level, branch, visited | {nxt})

    walk(seed, severity, Path(seed, reason), {seed})
    unique, seen = [], set()
    for p in finished:
        key = tuple((s.rule, s.dst) for s in p.steps)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def seeds_from(signals: list[dict], fragility: dict[str, dict], as_of: str) -> list[tuple[str, str, str, str]]:
    """(node, shock, severity, reason): serious signals up to as_of, plus companies rated weak."""
    seeds = {}
    for s in signals:
        if s.get("date", "") > as_of or s.get("severity") not in ("medium", "high"):
            continue
        t = s.get("signal_type")
        shock = "supply" if t in SUPPLY_SIGNALS else "credit" if t in CREDIT_SIGNALS else None
        if shock:
            key = (s["entity_id"], shock)
            if key not in seeds or s["severity"] == "high":
                seeds[key] = (s["entity_id"], shock, s["severity"],
                              f"{s['date']} {t}：{s.get('detail', '')}（{s.get('source_doc', '')}）")
    for code, row in fragility.items():
        if row.get("tier") == "weak" and (code, "credit") not in seeds:
            seeds[(code, "credit")] = (code, "credit", "medium", f"承压评分为弱：{row.get('reasons', '')[:80]}")
    return list(seeds.values())
