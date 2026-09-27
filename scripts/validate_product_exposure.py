"""Pre-registered test (docs/product_exposure_validation.md): does long-product exposure before the
2022–2023 property downturn explain which steel mills' gross margins fell most?

    python scripts/validate_product_exposure.py
Appends the result to docs/product_exposure_validation.md and writes the per-company table to
experiments/product_validation/data.csv. Pure Python, deterministic (seed 20260927).
"""
import csv
import random
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.product_layer import SPECIFIC_STEEL, exposure_as_of, exposure_table  # noqa: E402

AS_OF, BASE, SHOCK = "2022-04-30", "2021", "2023"
EXCLUDED = {"000709": "2021 年报无分品种", "601005": "各年均无分品种"}
SEED, PERMUTATIONS = 20260927, 10000
DOC = ROOT / "docs" / "product_exposure_validation.md"


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(x, y):
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    return cov / (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5


def permutation_p(x, y, observed, lower=True):
    rng = random.Random(SEED)
    y = list(y)
    hits = 0
    for _ in range(PERMUTATIONS):
        rng.shuffle(y)
        r = spearman(x, y)
        hits += (r <= observed) if lower else (r >= observed)
    return (hits + 1) / (PERMUTATIONS + 1)


def main() -> None:
    with (ROOT / "data" / "external" / "financials" / "indicators.csv").open(encoding="utf-8-sig", newline="") as f:
        gm = {(r["security_code"], r["fiscal_year"]): float(r["gross_margin"]) for r in csv.DictReader(f)
              if r["peer_group"] == "core" and r["gross_margin"] not in ("", None)}
    mills = sorted({(r["security_code"], r["security_name"]) for r in exposure_table() if r["tier"] == "core"})
    rows = []
    for code, name in mills:
        if code in EXCLUDED:
            continue
        e = exposure_as_of(code, AS_OF)
        spec = {k: v["share"] for k, v in (e or {}).get("products", {}).items() if k in SPECIFIC_STEEL}
        total = sum(spec.values())
        if not total or (code, BASE) not in gm or (code, SHOCK) not in gm:
            print(f"[skip] {name}: 数据不全")
            continue
        rows.append({"code": code, "name": name, "exposure_period": e["period"], "split_from": e["split_from"],
                     "L": spec.get("P_LONG", 0) / total, "S": spec.get("P_SPECIAL", 0) / total,
                     "F": spec.get("P_FLAT", 0) / total,
                     **{f"gm{y}": gm.get((code, y)) for y in ("2021", "2022", "2023", "2024")}})
    for r in rows:
        r["dgm"] = r["gm2023"] - r["gm2021"]
    n = len(rows)
    L, S, D = [r["L"] for r in rows], [r["S"] for r in rows], [r["dgm"] for r in rows]
    rho_l = spearman(L, D)
    p_l = permutation_p(L, D, rho_l, lower=True)
    rho_s = spearman(S, D)
    high = [r["dgm"] for r in rows if r["L"] >= 0.40]
    low = [r["dgm"] for r in rows if r["L"] < 0.20]
    med_high, med_low = statistics.median(high), statistics.median(low)
    h1 = "通过" if rho_l < 0 and p_l < 0.10 else "部分通过" if rho_l < 0 else "未通过"
    h2 = "通过" if med_high < med_low else "未通过"
    h3 = "通过" if rho_s >= 0 else "未通过"
    extra = {}
    for y in ("2022", "2024"):
        pairs = [(r["L"], r[f"gm{y}"] - r["gm2021"]) for r in rows if r[f"gm{y}"] is not None]
        extra[y] = (spearman([a for a, _ in pairs], [b for _, b in pairs]), len(pairs))

    out = ROOT / "experiments" / "product_validation"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "data.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    pct = lambda v: f"{v * 100:.1f}%"
    lines = ["", f"## 结果（{date.today().isoformat()} 运行，按上面写定的标准判定）", "",
             f"样本 {n} 家。", "",
             "| 编号 | 结果 | 判定 |", "| --- | --- | --- |",
             f"| H1 | ρ(L, ΔGM) = {rho_l:.3f}，单侧置换 p = {p_l:.4f} | {h1} |",
             f"| H2 | 长材为主（L≥40%，{len(high)} 家）ΔGM 中位数 {pct(med_high)}；长材很少（L<20%，{len(low)} 家）{pct(med_low)} | {h2} |",
             f"| H3 | ρ(S, ΔGM) = {rho_s:.3f} | {h3} |", "",
             f"只报告：ΔGM 取 2021→2022 时 ρ(L) = {extra['2022'][0]:.3f}（{extra['2022'][1]} 家）；"
             f"取 2021→2024 时 ρ(L) = {extra['2024'][0]:.3f}（{extra['2024'][1]} 家）。", "",
             "| 企业 | 长材 L | 特钢 S | 板材 F | 毛利率 2021 | 毛利率 2023 | ΔGM | 暴露口径 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in sorted(rows, key=lambda r: -r["L"]):
        src = r["exposure_period"][:4] + ("" if r["split_from"] == r["exposure_period"] else f"（细分取自{r['split_from'][:4]}）")
        lines.append(f"| {r['name']} | {pct(r['L'])} | {pct(r['S'])} | {pct(r['F'])} | {pct(r['gm2021'])} | {pct(r['gm2023'])} | "
                     f"{pct(r['dgm'])} | {src} |")
    text = "\n".join(lines) + "\n"
    print(text)
    with DOC.open("a", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
