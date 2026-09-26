"""Turn direction-1 documents into the two inputs of direction 3.

  * edges   - evidence-backed links between companies (guarantee, supply, service, lease, finance)
  * signals - dated risk signals on one company (supply disruption, capacity change, credit exposure ...)

Every row keeps the source document, page and evidence sentence, and how each company name
was mapped to a node (see src/entity_resolver.py), so any path found in direction 3 can be
checked step by step.

Edge direction convention (who provides what to whom):
  guarantee : src = guarantor, dst = guaranteed party   (if dst defaults, src must pay)
  supply / service / lease : src = supplier / provider, dst = buyer / user
  finance   : src = provider of financial services, dst = user
Severity rules are provisional and written out in `severity_rule`; direction 2 refines them
with each company's financial strength.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from src.entity_resolver import ROOT, Resolution, load_entities, node_id, resolve
from src.validity import (DEFAULT_MONTHS, guarantee_window, maintenance_window, pledge_window, related_window,
                          window)

TO_WAN = {"元": 1e-4, "千元": 0.1, "万元": 1.0, "百万元": 100.0, "亿元": 1e4}

TRADE = {  # category -> (edge_type, issuer is supplier?)
    "purchase_goods": ("supply", False), "sell_goods": ("supply", True),
    "receive_services": ("service", False), "provide_services": ("service", True),
    "lease_in": ("lease", False), "lease_out": ("lease", True),
    "financial_services": ("finance", False), "other": ("other", True),
}
SUBSIDIARY = {"wholly_owned_subsidiary", "controlled_subsidiary"}


@dataclass
class Edge:
    edge_type: str
    src_id: str
    src_name: str
    dst_id: str
    dst_name: str
    src_group: str
    dst_group: str
    same_group: int
    relationship: str
    status: str            # guarantee_provided | guarantee_limit | ... | estimate
    amount_wan: float | None
    prior_actual_wan: float | None
    category_text: str
    period: str            # estimate year or announcement date
    issuer_id: str
    announcement_date: str
    source_doc: str
    source_page: int | None
    evidence_text: str
    src_matched_by: str
    dst_matched_by: str
    src_scope: str
    dst_scope: str
    basis: str = "disclosed"   # disclosed (company announcement) | industry_approx (segment-level dependence)
    valid_from: str = ""       # in force from .. to (src/validity.py); empty = unbounded
    valid_to: str = ""


@dataclass
class Signal:
    entity_id: str
    entity_name: str
    group_id: str
    date: str
    signal_type: str       # supply_disruption | capacity_increase | capacity_reduction | project_delay | credit_exposure | credit_event | share_pledge
    severity: str          # info | low | medium | high
    severity_rule: str
    magnitude: float | None
    magnitude_unit: str
    detail: str
    source_doc: str
    source_page: int | None
    evidence_text: str
    valid_from: str = ""
    valid_to: str = ""


EDGE_FIELDS = [f.name for f in fields(Edge)]
SIGNAL_FIELDS = [f.name for f in fields(Signal)]


def to_wan(amount, unit) -> float | None:
    if amount is None or unit not in TO_WAN:
        return None
    return round(float(amount) * TO_WAN[unit], 4)


def issuer_node(doc: dict) -> Resolution:
    rows, _ = load_entities()
    code = doc.get("security_code") or ""
    if code in rows:
        return resolve(rows[code]["canonical_name"])
    return resolve(doc.get("company_name") or doc.get("security_name") or code)


def doc_kind(doc: dict) -> str:
    if "transactions" in doc:
        return "related_party"
    events = doc.get("events") or []
    first = events[0] if events else {}
    if "guarantor" in first or "external_guarantee_balance" in doc:
        return "guarantee"
    if "shareholder_name" in first:
        return "pledge"
    if "capacity_changes" in first or "project_name" in first:
        return "capacity"
    return "empty"


def _edge(edge_type, src: Resolution, dst: Resolution, **kw) -> Edge:
    return Edge(edge_type=edge_type, src_id=node_id(src), src_name=src.raw_name, dst_id=node_id(dst),
                dst_name=dst.raw_name, src_group=src.group_id or "", dst_group=dst.group_id or "",
                same_group=int(bool(src.group_id) and src.group_id == dst.group_id),
                src_matched_by=src.matched_by, dst_matched_by=dst.matched_by,
                src_scope=src.scope, dst_scope=dst.scope, **kw)


def edges_from(doc: dict, source_doc: str) -> tuple[list[Edge], int]:
    """-> (edges, records skipped because a party is not named)."""
    kind, issuer = doc_kind(doc), issuer_node(doc)
    common = dict(issuer_id=node_id(issuer), announcement_date=doc.get("announcement_date") or "",
                  source_doc=source_doc)
    out, skipped = [], 0
    if kind == "guarantee":
        for e in doc.get("events") or []:
            if not e.get("guarantor") or not e.get("guaranteed_party"):
                skipped += 1
                continue
            if e.get("event_type") == "guarantee_released":
                continue                      # a released guarantee no longer links the two companies
            rel = e.get("relationship") or ""
            src = resolve(e["guarantor"], issuer.entity_id)
            dst = resolve(e["guaranteed_party"], issuer.entity_id, rel)
            frm, to = guarantee_window(e, common["announcement_date"])
            out.append(_edge("guarantee", src, dst, relationship=rel, status=e["event_type"],
                             valid_from=frm, valid_to=to,
                             amount_wan=to_wan(e.get("guarantee_amount"), e.get("guarantee_unit")),
                             prior_actual_wan=None, category_text=e.get("guarantee_type") or "",
                             period=doc.get("announcement_date") or "", source_page=e.get("source_page"),
                             evidence_text=e.get("evidence_text") or "", **common))
    elif kind == "related_party":
        for t in doc.get("transactions") or []:
            if not t.get("counterparty"):
                skipped += 1
                continue
            rel = t.get("relationship") or ""
            edge_type, issuer_supplies = TRADE.get(t.get("transaction_category") or "other", ("other", True))
            other = resolve(t["counterparty"], issuer.entity_id, rel)
            src, dst = (issuer, other) if issuer_supplies else (other, issuer)
            frm, to = related_window(doc.get("estimate_year"), common["announcement_date"])
            out.append(_edge(edge_type, src, dst, relationship=rel, status="estimate",
                             valid_from=frm, valid_to=to,
                             amount_wan=to_wan(t.get("estimated_amount"), t.get("estimated_unit")),
                             prior_actual_wan=to_wan(t.get("prior_year_actual_amount"), t.get("prior_year_actual_unit")),
                             category_text=t.get("category_text") or t.get("goods_or_services") or "",
                             period=str(doc.get("estimate_year") or ""), source_page=t.get("source_page"),
                             evidence_text=t.get("evidence_text") or "", **common))
    return out, skipped


def _signal(res: Resolution, doc: dict, source_doc: str, record: dict, window_=None, **kw) -> Signal:
    announced = doc.get("announcement_date") or ""
    frm, to = window_ if window_ else window(None, None, announced, DEFAULT_MONTHS["project"])
    return Signal(entity_id=node_id(res), entity_name=res.raw_name, group_id=res.group_id or "",
                  date=announced, source_doc=source_doc, valid_from=frm, valid_to=to,
                  source_page=record.get("source_page"), evidence_text=record.get("evidence_text") or "", **kw)


def maintenance_severity(e: dict) -> tuple[str, str]:
    days = e.get("shutdown_days") or 0
    loss_t = e.get("output_loss_amount") if (e.get("output_loss_unit") or "").startswith("万吨") else None
    if days >= 30 or (loss_t or 0) >= 50:
        return "high", "停产>=30天 或 影响产量>=50万吨"
    if days >= 7 or (loss_t or 0) >= 10:
        return "medium", "停产>=7天 或 影响产量>=10万吨"
    return "low", "停产<7天且影响产量<10万吨（或未披露）"


def signals_from(doc: dict, source_doc: str) -> list[Signal]:
    kind, issuer = doc_kind(doc), issuer_node(doc)
    out = []
    if kind == "capacity":
        for e in doc.get("events") or []:
            et = e.get("event_type")
            if et == "maintenance":
                sev, rule = maintenance_severity(e)
                out.append(_signal(issuer, doc, source_doc, e, maintenance_window(e, doc.get("announcement_date") or ""),
                                   signal_type="supply_disruption", severity=sev,
                                   severity_rule=rule, magnitude=e.get("shutdown_days"), magnitude_unit="天",
                                   detail=f"{e.get('shutdown_facility') or ''} 影响 {e.get('output_loss_amount') or '-'}"
                                          f"{e.get('output_loss_unit') or ''} {e.get('output_loss_product') or ''}".strip()))
                continue
            if et in ("delay", "suspension", "termination"):
                sev = {"delay": "low", "suspension": "medium", "termination": "medium"}[et]
                out.append(_signal(issuer, doc, source_doc, e, signal_type="project_delay", severity=sev,
                                   severity_rule=f"{et}: 延期=low，暂停/终止=medium",
                                   magnitude=to_wan(e.get("investment_amount"), e.get("investment_unit")),
                                   magnitude_unit="万元(投资额)", detail=e.get("project_name") or ""))
            for c in e.get("capacity_changes") or []:
                increase = c.get("action") == "new"
                out.append(_signal(issuer, doc, source_doc, c,
                                   signal_type="capacity_increase" if increase else "capacity_reduction",
                                   severity="info", severity_rule="产能变化只作背景，严重程度由方向三结合供需关系判断",
                                   magnitude=c.get("capacity"), magnitude_unit=c.get("capacity_unit") or "",
                                   detail=f"{et} {c.get('facility_type') or ''} {c.get('product_name') or ''}".strip()))
    elif kind == "guarantee":
        balance = to_wan(doc.get("external_guarantee_balance"), doc.get("external_guarantee_unit"))
        if balance is not None:
            # Document-level cumulative balance of guarantees to parties OUTSIDE the consolidated
            # group (not the total, which also covers the issuer's own subsidiaries).
            announced = doc.get("announcement_date") or ""
            out.append(_signal(issuer, doc, source_doc, {}, window(announced, None, announced, 12),
                               signal_type="guarantee_balance", severity="info",
                               severity_rule="累计对外担保余额（合并报表外），用于承压评分的对外担保维度",
                               magnitude=balance, magnitude_unit="万元",
                               detail=f"累计对外担保余额 {balance / 1e4:.2f} 亿元"
                                      + (f"（总担保占净资产 {doc['total_guarantee_net_asset_ratio']}%）"
                                         if doc.get("total_guarantee_net_asset_ratio") is not None else "")))
        for e in doc.get("events") or []:
            rel, et = e.get("relationship") or "", e.get("event_type")
            if et == "guarantee_overdue":
                sev, rule, stype = "high", "逾期/代偿=high", "credit_event"
            elif et == "guarantee_released":
                continue
            elif rel in SUBSIDIARY:
                sev, rule, stype = "low", "为子公司担保=low", "credit_exposure"
            else:
                sev, rule, stype = "medium", "为非子公司（股东、兄弟公司、联营或无关方）担保=medium", "credit_exposure"
            announced = doc.get("announcement_date") or ""
            span = (window(announced, None, announced, DEFAULT_MONTHS["credit_event"]) if stype == "credit_event"
                    else guarantee_window(e, announced))
            out.append(_signal(resolve(e.get("guarantor") or issuer.raw_name, issuer.entity_id), doc, source_doc, e, span,
                               signal_type=stype, severity=sev, severity_rule=rule,
                               magnitude=to_wan(e.get("guarantee_amount"), e.get("guarantee_unit")),
                               magnitude_unit="万元", detail=f"{et} → {e.get('guaranteed_party') or ''}"))
    elif kind == "pledge":
        for e in doc.get("events") or []:
            if e.get("event_type") != "pledge":
                continue
            ratio = e.get("shareholder_holding_ratio") or 0
            sev = "high" if ratio >= 80 else "medium" if ratio >= 50 else "low"
            out.append(_signal(issuer, doc, source_doc, e, pledge_window(e, doc.get("announcement_date") or ""),
                           signal_type="share_pledge", severity=sev,
                               severity_rule="本次质押占其持股 >=80% high, >=50% medium",
                               magnitude=e.get("shares"), magnitude_unit="股",
                               detail=f"{e.get('shareholder_name') or ''} 质押给 {e.get('pledgee') or ''}"))
    return out


def doc_key(doc: dict) -> tuple:
    """The same announcement can sit in several Gold splits; count it once."""
    return (doc.get("security_code"), doc.get("announcement_number"), doc.get("announcement_date"), doc_kind(doc))


INDUSTRY_LINKS = ROOT / "data" / "reference" / "industry_links.csv"
MEMBERSHIP = ROOT / "data" / "reference" / "industry_membership.csv"
OVERRIDES = ROOT / "data" / "reference" / "industry_overrides.csv"
UNIVERSE = ROOT / "data" / "manifests" / "steel_universe.csv"


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def industry_of() -> dict[str, str]:
    """security_code -> industry node (S_*), from the universe segment, with explicit overrides."""
    seg = {r["segment"]: r["industry"] for r in _read(MEMBERSHIP)}
    out = {r["security_code"]: seg[r["segment"]] for r in _read(UNIVERSE) if r["segment"] in seg}
    out.update({r["security_code"]: r["industry"] for r in _read(OVERRIDES)})
    return out


def industry_edges() -> list[Edge]:
    """Approximate, segment-level links for relations announcements never disclose
    (a mill selling to an unrelated pipe maker). Always basis=industry_approx."""
    rows, _ = load_entities()
    blank = dict(relationship="", status="", amount_wan=None, prior_actual_wan=None, period="", issuer_id="",
                 announcement_date="", source_page=None, src_matched_by="industry", dst_matched_by="industry",
                 src_scope="self", dst_scope="self", basis="industry_approx")
    out = []
    for link in _read(INDUSTRY_LINKS):
        out.append(Edge(edge_type="industry", src_id=link["src_industry"], src_name=link["src_industry"][2:],
                        dst_id=link["dst_industry"], dst_name=link["dst_industry"][2:], src_group="", dst_group="",
                        same_group=0, category_text=f"{link['material']}（依赖度 {link['dependence']}）",
                        source_doc="data/reference/industry_links.csv", evidence_text=link["note"], **blank))
    for code, industry in sorted(industry_of().items()):
        entity = rows.get(code, {})
        out.append(Edge(edge_type="member_of", src_id=code, src_name=entity.get("short_name", code),
                        dst_id=industry, dst_name=industry[2:], src_group=entity.get("group_id", ""), dst_group="",
                        same_group=0, category_text="所属细分行业", source_doc="data/manifests/steel_universe.csv",
                        evidence_text="", **blank))
    return out


def as_row(record) -> dict:
    return {k: ("" if v is None else v) for k, v in asdict(record).items()}
