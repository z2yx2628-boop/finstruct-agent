"""Demonstration case (NOT a validation): run one real historical price shock through the scenario engine
and write it up, so the report and the defence can show the whole chain end to end.

    python scripts/scenario_case.py                      # 2024-09-30, coke 20-day +13%
    python scripts/scenario_case.py --day 2024-09-30 --product P_COKE
Writes docs/scenario_case_<day>_<product>.md. Uses the fragility snapshot of that day if it exists
(python scripts/update_all.py --as-of <day> --offline), otherwise the latest earlier one, and says which.
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.price_shock import WINDOW  # noqa: E402
from src.scenario import CAVEAT, RULES, build, product_map  # noqa: E402
from src.sources import titles  # noqa: E402
from src.validity import is_active  # noqa: E402

GRADE = {"A": "A 披露确认", "B": "B 部分确认", "C": "C 行业推断", "—": "—"}
TIER = {"weak": "弱", "medium": "中", "strong": "强", "": "未评分"}


def series(symbol: str) -> dict[str, float]:
    with (ROOT / "data" / "external" / "prices" / f"{symbol}.csv").open(encoding="utf-8-sig", newline="") as f:
        return {r["date"][:10]: float(r["close"]) for r in csv.DictReader(f) if r.get("close")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2024-09-30")
    ap.add_argument("--product", default="P_COKE")
    args = ap.parse_args()
    day, pid = args.day, args.product
    snaps = sorted(p.name for p in (ROOT / "data" / "snapshots").glob("*") if (p / "fragility.csv").exists())
    snap = max(s for s in snaps if s <= day)
    with (ROOT / "data" / "snapshots" / snap / "fragility.csv").open(encoding="utf-8-sig", newline="") as f:
        fragility = {r["security_code"]: r for r in csv.DictReader(f)}
    with (ROOT / "data" / "chain" / "live" / "edges.csv").open(encoding="utf-8-sig", newline="") as f:
        edges = [e for e in csv.DictReader(f) if is_active(e, day)]
    kind = "price_up"
    rows = []
    for p in (v for v in product_map().values() if v["price_symbol"]):
        s = series(p["price_symbol"])
        days = sorted(s)
        i = days.index(max(d for d in days if d <= day))
        pick = lambda k: (days[k], s[days[k]]) if 0 <= k < len(days) else ("", None)
        before, now, after20, after60 = pick(i - WINDOW), pick(i), pick(i + 20), pick(i + 60)
        ret = now[1] / before[1] - 1
        if p["product_id"] == pid:
            kind = "price_up" if ret > 0 else "price_down"
        rows.append((p["name"], before, now, ret, after20, after60))
    result = build(kind, day, fragility, edges, product_id=pid)
    names = {n["node"]: n["name"] for n in result["nodes"]}
    name = product_map()[pid]["name"]

    out = [f"# 演示案例：{day} {name}价格冲击（情景演示，不是验证）", "",
           f"> {CAVEAT}", "",
           "本文件由 `scripts/scenario_case.py` 生成，用来展示系统在一个真实的历史价格冲击下能给出什么样的链条。"
           "它**不**用于证明系统能预测风险：产品层只做了两次预先登记的检验（均未达显著），此后不再用案例补做检验。", "",
           f"- 评估日：{day}；承压等级取快照 {snap}" + ("" if snap == day else "（评估日当天没有快照，取最近的更早快照）") + "；",
           "- 产品构成：评估日可得的最新年报（`src/product_layer.exposure_as_of`）；公告关系：评估日有效的实时图谱边。", "",
           f"## 1. 冲击：近 {WINDOW} 个交易日产品价格", "",
           f"| 产品 | {WINDOW} 日前 | 评估日 | 涨跌 |", "| --- | --- | --- | --- |"]
    for n, before, now, ret, _, _ in rows:
        out.append(f"| {n} | {before[1]:.1f}（{before[0]}） | {now[1]:.1f}（{now[0]}） | {ret:+.1%} |")
    out += ["", f"情景设定：**{result['title']}**。注意同期所有产品一起上涨，这是一次普涨，不是只影响单一原料的冲击。", "",
            "## 2. 情景链条", "", "| 从 | 到 | 关系 | 证据等级 | 影响 | 依据 |", "| --- | --- | --- | --- | --- | --- |"]
    for e in result["edges"]:
        evidence = e["evidence"]
        stem = evidence.split(" 第")[0]
        if stem in titles():
            evidence = evidence.replace(stem, titles()[stem], 1)
        out.append(f"| {names[e['src']]} | {names[e['dst']]} | {RULES[e['rule']]} | {GRADE.get(e['grade'], e['grade'])} | "
                   f"{e['effect']} | {evidence[:90].replace('|', '/')} |")
    out += ["", "## 3. 暴露企业（按承压由弱到强、暴露由大到小，仅提示关注顺序）", "",
            "| 企业 | 承压 | 影响 | 证据等级 |", "| --- | --- | --- | --- |"]
    out += [f"| {r['name']} | {TIER.get(r['tier'], '未评分')} | {r['effect']} | {GRADE.get(r['grade'], r['grade'])} |"
            for r in result["companies"]]
    out += ["", "## 4. 事后价格走势（仅描述，不作为验证）", "",
            "| 产品 | 评估日 | 20 个交易日后 | 60 个交易日后 |", "| --- | --- | --- | --- |"]
    for n, _, now, _, a20, a60 in rows:
        fmt = lambda x: f"{x[1]:.1f}（{x[0]}，{x[1] / now[1] - 1:+.1%}）" if x[1] else "—"
        out.append(f"| {n} | {now[1]:.1f} | {fmt(a20)} | {fmt(a60)} |")
    out += ["", "## 5. 这个案例说明什么、不说明什么", "",
            "- **说明**：一个真实的产品价格冲击出现时，系统能在同一天给出完整、带证据等级的链条：谁卖这个产品（公司自己披露的收入构成），"
            "谁在公告里披露过采购它，哪些钢厂承压最弱，成本若转嫁会落到哪些钢材和下游行业、哪些下游企业在年报里点名钢材为主要原材料。",
            "- **不说明**：冲击会不会真的造成损失、损失多大。价格冲击可能很快回落（见第 4 节），企业也可能通过套期保值、长协价格、"
            "调整产品结构来缓冲；这些都不在系统的证据范围内。",
            "- 按证据等级阅读：A、B 级是公告或公司自己披露的事实；C 级（行业用钢、未披露采购比例的钢厂）是按行业常识推断的情景。"]
    path = ROOT / "docs" / f"scenario_case_{day}_{pid}.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:12]))
    print(f"... -> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
