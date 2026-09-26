import csv

from src.fragility_view import SNAP, data_sources, explain, guarantee_evidence, snapshot_meta


def test_breakdown_reproduces_every_v1_snapshot_score():
    checked = 0
    for folder in sorted(SNAP.glob("*")):
        if not (folder / "fragility.csv").exists() or snapshot_meta(folder)["version"] != "v1":
            continue
        with (folder / "fragility.csv").open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                detail = explain(folder, row["security_code"])
                if detail and row["total_score"]:
                    assert abs(detail["total_recomputed"] - float(row["total_score"])) < 0.05, (folder.name, row["security_name"])
                    checked += 1
    assert checked > 100


def test_antai_breakdown_shows_red_line_and_its_announcement():
    folder = SNAP / "2025-01-31"
    detail = explain(folder, "600408")
    assert any("对外担保" in rule for rule in detail["rules"])
    balance = [g for g in guarantee_evidence(folder, "600408") if g["类型"] == "累计对外担保余额"]
    assert balance and balance[0]["金额(亿元)"] == 28.58 and "新泰钢铁" in balance[0]["来源"]
    sources = dict(data_sources(detail["row"]))
    assert sources["财报期"].startswith("2024-09-30") and sources["可使用日"].startswith("2024-10-31")


def test_method_version_is_recorded_or_inferred():
    assert snapshot_meta(SNAP / "2026-09-24")["version"] == "v0"
    assert snapshot_meta(SNAP / "2026-09-26")["version"] == "v1"
