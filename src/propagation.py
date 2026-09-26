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

from src.validity import is_active
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
    amount_wan: float | None = None


@dataclass
class Path:
    seed: str
    seed_reason: str
    steps: list[Step] = field(default_factory=list)


def lower(level: str) -> str | None:
    i = LEVELS.index(level)
    return LEVELS[i - 1] if i > 0 else None


def group_proxies(fragility: dict[str, dict], equity: dict[str, float], groups: dict[str, str],
                  listed: set[str]) -> dict[str, dict]:
    """Unlisted parent groups (鞍钢集团, 中国宝武 …) publish no accounts here. Their proxy tier is the
    equity-weighted average fragility score of the group's listed members (same thresholds:
    >=60 weak, >=40 medium, else strong), marked proxy=1 so it is never shown as a real score."""
    from src.entity_resolver import load_entities

    rows, _ = load_entities()
    by_group: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for code in listed:
        r = fragility.get(code)
        if r and r.get("total_score") not in (None, "") and groups.get(code):
            weight = equity.get(code) or 0.0
            by_group[groups[code]].append((code, float(r["total_score"]), max(weight, 0.0)))
    proxies = {}
    for entity, row in rows.items():
        members = by_group.get(row.get("group_id"))
        if row.get("entity_type") != "parent_group" or not members:
            continue
        total_w = sum(w for _, _, w in members)
        score = (sum(s * w for _, s, w in members) / total_w) if total_w else sum(s for _, s, _ in members) / len(members)
        tier = "weak" if score >= 60 else "medium" if score >= 40 else "strong"
        proxies[entity] = {"tier": tier, "total_score": round(score, 1), "proxy": 1,
                           "reasons": "集团参照：上市成员按净资产加权 " + "、".join(
                               f"{c}:{s:.0f}" for c, s, _ in sorted(members, key=lambda m: -m[2])[:4])}
    return proxies


class Graph:
    def __init__(self, edges: list[dict], fragility: dict[str, dict], equity: dict[str, float],
                 groups: dict[str, str], listed: set[str], proxies: bool = True):
        self.fragility, self.equity, self.groups, self.listed = fragility, equity, groups, listed
        self.proxy = group_proxies(fragility, equity, groups, listed) if proxies else {}
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
        return (self.fragility.get(node, {}).get("tier") or self.proxy.get(node, {}).get("tier") or "unknown")

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
            amount = edge.get("amount_wan")
            step = Step(rule, node, nxt, shock, level, tier, "continue", edge.get("basis", "disclosed"),
                        evidence_of(edge), amount_wan=float(amount) if amount not in (None, "") else None)
            branch = Path(path.seed, path.seed_reason, path.steps + [step])
            if rule != "R4" and not graph.material(edge, nxt):
                step.decision, step.note = "immaterial", f"金额低于对方净资产的{MATERIALITY:.0%}"
                finished.append(branch)
                continue
            if nxt in graph.proxy and nxt not in graph.fragility:
                step.note = f"集团参照等级（{graph.proxy[nxt]['total_score']}分）"
            if tier == "strong":
                step.decision, step.note = "absorbed", (step.note + "；" if step.note else "") + "承压为强，风险在此被吸收"
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


SUBSIDIARY = {"wholly_owned_subsidiary", "controlled_subsidiary"}


def opaque_guarantee_seeds(edges: list[dict], fragility: dict[str, dict], equity: dict[str, float],
                           as_of: str) -> dict[tuple[str, str], tuple[str, str, str, str]]:
    """A non-subsidiary that receives guarantees but has no rating of its own is an opaque risk
    source (its accounts are not public). Severity follows the guarantee's size relative to the
    guarantor's equity: >=50% high, >=10% medium (安泰集团 -> 山西新泰钢铁 is ~170%)."""
    totals: dict[tuple[str, str], float] = defaultdict(float)
    for e in edges:
        if (e.get("edge_type") == "guarantee" and e.get("relationship") not in SUBSIDIARY
                and e.get("dst_id") not in fragility and e.get("amount_wan") not in (None, "")
                and is_active(e, as_of)):
            totals[(e["src_id"], e["dst_id"])] += float(e["amount_wan"])
    seeds = {}
    for (guarantor, party), amount_wan in totals.items():
        eq = equity.get(guarantor)
        if not eq or eq <= 0:
            continue
        ratio = amount_wan * 1e4 / eq
        severity = "high" if ratio >= 0.5 else "medium" if ratio >= 0.1 else None
        if severity:
            seeds[(party, "credit")] = (party, "credit", severity,
                                        f"未评分的非子公司被担保方（财务不公开）：获担保 {amount_wan / 1e4:.2f} 亿元，"
                                        f"占担保方净资产 {ratio:.0%}")
    return seeds


def seeds_from(signals: list[dict], fragility: dict[str, dict], as_of: str, edges: list[dict] | None = None,
               equity: dict[str, float] | None = None) -> list[tuple[str, str, str, str]]:
    """(node, shock, severity, reason): serious signals up to as_of, companies rated weak, and
    opaque guaranteed parties (see opaque_guarantee_seeds)."""
    seeds = dict(opaque_guarantee_seeds(edges or [], fragility, equity or {}, as_of))
    for s in signals:
        if not is_active(s, as_of) or s.get("severity") not in ("medium", "high"):
            continue
        t = s.get("signal_type")
        shock = "supply" if t in SUPPLY_SIGNALS else "credit" if t in CREDIT_SIGNALS else None
        if shock:
            key = (s["entity_id"], shock)
            if key not in seeds or (s["severity"] == "high" and seeds[key][2] != "high"):
                seeds[key] = (s["entity_id"], shock, s["severity"],
                              f"{s['date']} {t}：{s.get('detail', '')}（{s.get('source_doc', '')}）")
    for code, row in fragility.items():
        if row.get("tier") == "weak" and (code, "credit") not in seeds:
            seeds[(code, "credit")] = (code, "credit", "medium", f"承压评分为弱：{row.get('reasons', '')[:80]}")
    return list(seeds.values())


SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}
TIER_WEIGHT = {"weak": 1.0, "medium": 0.5, "strong": 0.0}


def summarize(paths: list[Path], listed: set[str]) -> tuple[list[dict], list[dict]]:
    """Make 500 raw branches readable.

    key paths : each path is cut after its last LISTED company; what lies beyond (unlisted group
                subsidiaries) is folded into a count and an amount. Identical cut paths merge.
                score = seed severity x (1 + log10(1 + amount in 亿元)) x sum of listed tiers passed
                (weak 1, medium 0.5, strong 0): paths that reach weak listed companies with large
                amounts rank first; every factor is shown so the ranking stays explainable.
    local reach: per seed, the unlisted related parties reached directly (no listed company on the way).
    """
    import math

    keyed: dict[tuple, dict] = {}
    local: dict[str, dict] = {}
    for p in paths:
        last = max((i for i, s in enumerate(p.steps) if s.dst in listed), default=None)
        if last is None:
            entry = local.setdefault(p.seed, {"seed": p.seed, "reason": p.seed_reason, "parties": set(), "amount_wan": 0.0})
            entry["parties"].update(s.dst for s in p.steps)
            entry["amount_wan"] += sum(s.amount_wan or 0 for s in p.steps[:1])
            continue
        head, tail = p.steps[:last + 1], p.steps[last + 1:]
        key = (p.seed,) + tuple((s.rule, s.dst) for s in head)
        entry = keyed.setdefault(key, {"seed": p.seed, "reason": p.seed_reason, "steps": head,
                                       "beyond": set(), "beyond_amount_wan": 0.0})
        entry["beyond"].update(s.dst for s in tail)
        entry["beyond_amount_wan"] += sum(s.amount_wan or 0 for s in tail[:1])
    ranked = []
    for entry in keyed.values():
        amount_yi = sum(s.amount_wan or 0 for s in entry["steps"]) / 1e4
        reach = sum(TIER_WEIGHT.get(s.dst_tier, 0) for s in entry["steps"] if s.dst in listed)
        severity = entry["steps"][0].severity
        entry["score"] = round(SEVERITY_WEIGHT[severity] * (1 + math.log10(1 + amount_yi)) * reach, 2)
        entry["amount_yi"] = round(amount_yi, 2)
        entry["listed_reach"] = reach
        ranked.append(entry)
    ranked.sort(key=lambda e: -e["score"])
    # The same listed companies reached in the same order via different unlisted group
    # subsidiaries is one finding: keep the best-scoring route, count the alternatives.
    findings, by_listed = [], {}
    for entry in ranked:
        key = (entry["seed"],) + tuple(s.dst for s in entry["steps"] if s.dst in listed)
        if key in by_listed:
            by_listed[key]["alternatives"] += 1
            by_listed[key]["alternative_routes"].append("+".join(s.rule for s in entry["steps"]))
            continue
        entry["alternatives"] = 0
        entry["alternative_routes"] = []
        by_listed[key] = entry
        findings.append(entry)
    ranked = findings
    reach_rows = sorted(local.values(), key=lambda e: -len(e["parties"]))
    return ranked, reach_rows
