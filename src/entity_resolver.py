"""Map company names found in announcements to one node id (shared by directions 1-3).

"湘钢集团", "湘潭钢铁集团有限公司" and "湘钢集团及其子公司" must become the same node,
otherwise a guarantee edge from direction 1 cannot be joined to financial data (direction 2)
or followed along the chain (direction 3).

Resolution order, every step reported in `matched_by` so the mapping stays auditable:
  1. self reference ("本公司", "公司") -> the issuer of the announcement
  2. exact canonical name / short name / alias (after width and whitespace normalisation)
  3. group token ("涟钢物流", "唐山首钢京唐西山焦化" -> group known, entity unknown);
     short tokens that are ambiguous (中信, 南钢 ...) only match at the start of the name
  4. relationship stated in the announcement: a controlling shareholder, a sister company
     or a subsidiary is in the issuer's group ("宏基检测", sister_company of 酒钢宏兴)
Names that match nothing return entity_id=None and group_id=None: never guessed.
`node_id()` gives unresolved names a stable node of their own ("N_<name>") for the graph.

The "scope" records what the name covers: the entity itself, it plus subsidiaries,
only its subsidiaries, or its associates ("宝武集团之联营企业").
"""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTITIES = ROOT / "data" / "reference" / "entities.csv"
PREFIXES = ROOT / "data" / "reference" / "group_prefixes.csv"

SELF_NAMES = {"本公司", "公司", "上市公司", "本集团"}
TRAILING_NOTE = re.compile(r"[（(][^（）()]*[)）]$")
SCOPE_SUFFIXES = [  # longest first
    ("及其下属子公司", "self_and_subsidiaries"), ("及其控制的企业", "self_and_subsidiaries"),
    ("及下属子公司", "self_and_subsidiaries"), ("及其子公司", "self_and_subsidiaries"),
    ("及子分公司", "self_and_subsidiaries"), ("及下属企业", "self_and_subsidiaries"),
    ("及子公司", "self_and_subsidiaries"),
    ("其他子公司", "subsidiaries"), ("下属子公司", "subsidiaries"),
    ("之子分公司", "subsidiaries"), ("之子公司", "subsidiaries"), ("的子公司", "subsidiaries"),
    ("之联营企业", "associates"), ("之合营企业", "associates"),
]


@dataclass(frozen=True)
class Resolution:
    raw_name: str
    base_name: str
    scope: str                 # self | self_and_subsidiaries | subsidiaries | associates
    entity_id: str | None
    group_id: str | None
    matched_by: str            # self_reference | exact | alias | group_token | relationship | unresolved
    note: str = ""


def normalize(name: str) -> str:
    text = unicodedata.normalize("NFKC", name or "")
    return re.sub(r"\s+", "", text)


def split_scope(name: str) -> tuple[str, str, str]:
    """-> (base name, scope, trailing note such as the category in brackets)."""
    text, notes = normalize(name), []
    while True:
        m = TRAILING_NOTE.search(text)
        if not m or m.start() == 0:
            break
        notes.insert(0, m.group(0)[1:-1])
        text = text[: m.start()]
    scope = "self"
    for suffix, kind in SCOPE_SUFFIXES:
        if text.endswith(suffix) and len(text) > len(suffix):
            text, scope = text[: -len(suffix)], kind
            break
    return text, scope, "；".join(notes)


@lru_cache(maxsize=None)
def load_entities(path: Path = ENTITIES) -> tuple[dict[str, dict], dict[str, tuple[str, str]]]:
    """-> (entity_id -> row, normalized name -> (entity_id, how))."""
    rows, index = {}, {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows[row["entity_id"]] = row
            names = [(row["canonical_name"], "exact"), (row["short_name"], "exact")]
            names += [(a, "alias") for a in row["aliases"].split("|") if a]
            for name, how in names:
                key = normalize(name)
                if key in index and index[key][0] != row["entity_id"]:
                    raise ValueError(f"name {name!r} maps to both {index[key][0]} and {row['entity_id']}")
                index[key] = (row["entity_id"], how)
    return rows, index


@lru_cache(maxsize=None)
def load_prefixes(path: Path = PREFIXES) -> list[tuple[str, str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [(r["token"], r["group_id"], r["match"]) for r in csv.DictReader(f)]
    return sorted(rows, key=lambda p: -len(p[0]))


IN_ISSUER_GROUP = {"parent_or_controlling_shareholder", "sister_company",
                   "wholly_owned_subsidiary", "controlled_subsidiary"}


def resolve(name: str, issuer_id: str | None = None, relationship: str | None = None) -> Resolution:
    rows, index = load_entities()
    base, scope, note = split_scope(name)
    if base in SELF_NAMES and issuer_id:
        return Resolution(name, base, scope, issuer_id, rows[issuer_id]["group_id"], "self_reference", note)
    if base in index:
        entity_id, how = index[base]
        return Resolution(name, base, scope, entity_id, rows[entity_id]["group_id"], how, note)
    for token, group_id, match in load_prefixes():
        if base.startswith(token) or (match == "contains" and token in base):
            return Resolution(name, base, scope, None, group_id, "group_token", note)
    if relationship in IN_ISSUER_GROUP and issuer_id in rows:
        return Resolution(name, base, scope, None, rows[issuer_id]["group_id"], "relationship", note)
    return Resolution(name, base, scope, None, None, "unresolved", note)


def node_id(res: Resolution) -> str:
    return res.entity_id or f"N_{res.base_name}"


def same_group(a: str, b: str) -> bool:
    rows, _ = load_entities()
    ga, gb = rows.get(a, {}).get("group_id"), rows.get(b, {}).get("group_id")
    return bool(ga) and ga == gb
