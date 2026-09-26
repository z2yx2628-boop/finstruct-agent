"""Turn internal evidence references ("outputs/.../analysis_007_000709_related_estimate.json 第2页")
into what a reader can check: 《announcement title》(company, date) 第2页."""
from __future__ import annotations

import csv
import re
from functools import lru_cache

from src.entity_resolver import ROOT, load_entities

JSON_REF = re.compile(r"\S*?([A-Za-z0-9_]+)(?:/prediction)?\.json")


@lru_cache(maxsize=1)
def titles() -> dict[str, str]:
    out = {}
    for path in (ROOT / "data" / "manifests").glob("*_sources.csv"):
        with path.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                name = (r.get("file_name") or "").rsplit(".", 1)[0]
                title = r.get("announcement_title") or r.get("title")
                if name and title:
                    out[name] = f"{r.get('security_name', '')}《{title}》（{r.get('announcement_date', '')}）"
    return out


GROUP_REF = re.compile(r"data/reference/entities\.csv：同属集团 (G_[A-Z0-9_]+)")


@lru_cache(maxsize=1)
def group_names() -> dict[str, str]:
    rows, _ = load_entities()
    out = {}
    for row in rows.values():
        if row["entity_type"] == "parent_group" and not row["parent_id"]:
            out.setdefault(row["group_id"], row["short_name"])
    return out


def readable(evidence: str, limit: int = 200) -> str:
    """Announcement title instead of a prediction file path, group name instead of a group id,
    table line breaks collapsed."""
    def swap(match: re.Match) -> str:
        return titles().get(match.group(1), match.group(0))
    text = GROUP_REF.sub(lambda m: f"同属{group_names().get(m.group(1), m.group(1))}（企业名称对照表，实际控制人口径）",
                         evidence or "")
    text = JSON_REF.sub(swap, text, count=1)
    return re.sub(r"\s+", " ", text).strip()[:limit]
