"""Second, final pre-registered test of the product layer (docs/product_price_validation.md): do steel mills'
share prices follow the steel product they sell? Pure Python, deterministic (seed 20260927).

    python scripts/validate_product_prices.py
"""
import csv
import random
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.validate_product_exposure import EXCLUDED, ranks, spearman  # noqa: E402
from src.product_layer import SPECIFIC_STEEL, exposure_as_of, exposure_table  # noqa: E402

AS_OF, START, END = "2022-04-30", "2022-05-06", "2025-04-25"
SEED, PERMUTATIONS, ALPHA, JUMP, PLACEBO_SHIFT = 20260927, 10000, 0.05, 0.25, 26
DOC = ROOT / "docs" / "product_price_validation.md"


def closes(path: Path) -> dict[str, float]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {r["date"][:10]: float(r["close"]) for r in csv.DictReader(f) if r.get("close") not in ("", None)}


def week_key(day: str) -> tuple[int, int]:
    return date.fromisoformat(day).isocalendar()[:2]


def weekly(series: dict[str, float], days: list[str]) -> dict[tuple, float]:
    """Close on the last of `days` in each ISO week (days = common trading days)."""
    out = {}
    for d in days:
        if d in series:
            out[week_key(d)] = series[d]
    return out


def returns(w: dict[tuple, float], weeks: list[tuple]) -> dict[tuple, float]:
    out = {}
    for prev, cur in zip(weeks, weeks[1:]):
        if prev in w and cur in w and w[prev]:
            out[cur] = w[cur] / w[prev] - 1
    return out


def ols_slope(x, y):
    mx, my = statistics.mean(x), statistics.mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx
    resid = [c - my - b * (a - mx) for a, c in zip(x, y)]
    se = (sum(e * e for e in resid) / (len(x) - 2) / sxx) ** 0.5
    return b, (b / se if se else 0.0)


def perm_p(x, y, observed):
    rng = random.Random(SEED)
    y = list(y)
    hits = 0
    for _ in range(PERMUTATIONS):
        rng.shuffle(y)
        hits += spearman(x, y) >= observed
    return (hits + 1) / (PERMUTATIONS + 1)


def main() -> None:
    rb, hc = closes(ROOT / "data" / "external" / "prices" / "RB0.csv"), closes(ROOT / "data" / "external" / "prices" / "HC0.csv")
    mills = []
    for code, name in sorted({(r["security_code"], r["security_name"]) for r in exposure_table() if r["tier"] == "core"}):
        if code in EXCLUDED:
            continue
        e = exposure_as_of(code, AS_OF)
        spec = {k: v["share"] for k, v in (e or {}).get("products", {}).items() if k in SPECIFIC_STEEL}
        total = sum(spec.values())
        path = ROOT / "data" / "external" / "market" / f"{code}.csv"
        if not total or not path.exists():
            print(f"[skip] {name}: 暴露或行情缺失")
            continue
        mills.append({"code": code, "name": name, "L": spec.get("P_LONG", 0) / total, "F": spec.get("P_FLAT", 0) / total,
                      "px": closes(path)})
    days = sorted(d for d in set(rb) & set(hc) if START <= d <= END)
    weeks = sorted({week_key(d) for d in days})
    spread_w = returns(weekly(rb, days), weeks)
    hc_w = returns(weekly(hc, days), weeks)
    spread = {k: spread_w[k] - hc_w[k] for k in spread_w if k in hc_w}
    stock = {}
    for m in mills:
        r = returns(weekly(m["px"], days), weeks)
        stock[m["code"]] = {k: v for k, v in r.items() if abs(v) <= JUMP}
    peer = {}
    for k in weeks:
        vals = [stock[m["code"]][k] for m in mills if k in stock[m["code"]]]
        if len(vals) >= len(mills) // 2:
            peer[k] = statistics.median(vals)
    order = [k for k in weeks if k in spread]
    shifted = {order[i]: spread[order[i - PLACEBO_SHIFT]] for i in range(PLACEBO_SHIFT, len(order))}

    def slope(m, x_series):
        keys = [k for k in order if k in x_series and k in peer and k in stock[m["code"]]]
        return ols_slope([x_series[k] for k in keys], [stock[m["code"]][k] - peer[k] for k in keys]) + (len(keys),)

    for m in mills:
        m["g"], m["t"], m["n"] = slope(m, spread)
        m["g_placebo"], _, _ = slope(m, shifted)
        m["g_rb"], _, _ = slope(m, {k: rb_w for k, rb_w in returns(weekly(rb, days), weeks).items()})
        m["g_hc"], _, _ = slope(m, hc_w)
    L, G, P = [m["L"] for m in mills], [m["g"] for m in mills], [m["g_placebo"] for m in mills]
    rho, p = spearman(L, G), None
    p = perm_p(L, G, rho)
    rho_p = spearman(L, P)
    p_placebo = perm_p(L, P, rho_p)
    high = [m["g"] for m in mills if m["L"] >= 0.40]
    low = [m["g"] for m in mills if m["L"] < 0.20]
    h1 = "通过" if rho > 0 and p < ALPHA else "部分通过" if rho > 0 else "未通过"
    h2 = "通过" if statistics.median(high) > statistics.median(low) else "未通过"
    h3 = "通过" if p_placebo >= ALPHA else "未通过"

    out = ROOT / "experiments" / "product_validation"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "price_sensitivity.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "name", "L", "F", "g", "t", "n", "g_placebo", "g_rb", "g_hc"], lineterminator="\n")
        w.writeheader()
        w.writerows({k: m[k] for k in w.fieldnames} for m in mills)
    pct = lambda v: f"{v * 100:.1f}%"
    lines = ["", f"## 结果（{date.today().isoformat()} 运行，按上面写定的标准判定）", "",
             f"样本 {len(mills)} 家；检验期 {len(order)} 周（{START} 至 {END}）。", "",
             "| 编号 | 结果 | 判定 |", "| --- | --- | --- |",
             f"| H1 | ρ(L, g) = {rho:.3f}，单侧置换 p = {p:.4f}（标准 p < {ALPHA}） | {h1} |",
             f"| H2 | 长材为主（L≥40%，{len(high)} 家）g 中位数 {statistics.median(high):.3f}；长材很少（L<20%，{len(low)} 家）{statistics.median(low):.3f} | {h2} |",
             f"| H3 | 安慰剂（价差错开 {PLACEBO_SHIFT} 周）ρ(L, g′) = {rho_p:.3f}，单侧 p = {p_placebo:.4f} | {h3} |", "",
             "| 企业 | 长材 L | 板材 F | g（相对价差） | t 值 | 周数 | 只用螺纹 | 只用热卷 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for m in sorted(mills, key=lambda m: -m["L"]):
        lines.append(f"| {m['name']} | {pct(m['L'])} | {pct(m['F'])} | {m['g']:.3f} | {m['t']:.2f} | {m['n']} | {m['g_rb']:.3f} | {m['g_hc']:.3f} |")
    text = "\n".join(lines) + "\n"
    print(text)
    with DOC.open("a", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
