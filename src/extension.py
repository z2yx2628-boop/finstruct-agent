"""Extension peer groups (焦煤焦炭上游、下游用钢龙头): scored within their own group by scripts/score_extension.py.
Never part of the 24-mill ranking. Used to colour these companies in scenarios and to list them in 企业档案."""
from __future__ import annotations

import csv
import json

from src.entity_resolver import ROOT

SNAP = ROOT / "data" / "snapshots_extension"
LAYER_LABEL = {"extension_upstream": "扩展组·焦煤焦炭", "extension_downstream": "扩展组·下游龙头"}


def snapshot_for(as_of: str):
    folders = sorted(p for p in SNAP.glob("*") if p.is_dir() and p.name <= as_of and any(p.glob("fragility_*.csv")))
    return folders[-1] if folders else None


def rows(as_of: str) -> dict[str, dict]:
    folder = snapshot_for(as_of)
    out = {}
    if folder is None:
        return out
    caveat = json.loads((folder / "meta.json").read_text(encoding="utf-8")).get("caveat", {}) if (folder / "meta.json").exists() else {}
    for path in folder.glob("fragility_*.csv"):
        with path.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("tier"):
                    layer = r.get("peer_group", "").replace("extension_", "")
                    out[r["security_code"]] = {**r, "snapshot": folder.name, "caveat": caveat.get(layer, "")}
    return out


def merged(fragility: dict[str, dict], as_of: str) -> dict[str, dict]:
    """Core/other rows win; extension rows only fill companies the core snapshot does not score."""
    return {**{k: v for k, v in rows(as_of).items()}, **fragility}
