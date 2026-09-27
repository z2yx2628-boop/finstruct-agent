"""Product layer data: what each company sells (B-grade exposure) and the daily prices of the chain's products.

    python scripts/build_product_exposure.py            # fetch what is missing, rebuild the tables
    python scripts/build_product_exposure.py --refresh  # re-fetch everything (after new annual reports)
    python scripts/build_product_exposure.py --prices   # only update the product prices (daily job)

Reads  data/manifests/steel_universe.csv (42 chain companies) + data/reference/downstream_users.csv
Writes data/external/exposure/raw/<code>.csv            东方财富 主营构成, as fetched
       data/external/exposure/product_exposure.csv      one row per company x annual period x product
       data/external/exposure/unmapped.csv              companies whose disclosure names no known product
       data/external/prices/<symbol>.csv                新浪 futures main contract, daily
"""
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.product_layer import exposures_by_period, products  # noqa: E402

EXP = ROOT / "data" / "external" / "exposure"
RAW = EXP / "raw"
PRICES = ROOT / "data" / "external" / "prices"
FIELDS = ["security_code", "security_name", "tier", "segment", "period", "available_by", "basis", "product_id", "product",
          "revenue_share", "gross_margin", "items", "unmapped_share", "grade", "source"]


def companies() -> list[dict]:
    out = []
    with (ROOT / "data" / "manifests" / "steel_universe.csv").open(encoding="utf-8-sig", newline="") as f:
        out += [{"code": r["security_code"], "name": r["security_name"], "tier": r["tier"], "segment": r["segment"]}
                for r in csv.DictReader(f)]
    with (ROOT / "data" / "reference" / "downstream_users.csv").open(encoding="utf-8-sig", newline="") as f:
        out += [{"code": r["security_code"], "name": r["security_name"], "tier": "end_user", "segment": r["sector"]}
                for r in csv.DictReader(f)]
    return out


def em_symbol(code: str) -> str:
    return ("SH" if code.startswith(("6", "9")) else "BJ" if code.startswith(("4", "8")) else "SZ") + code


def fetch_composition(refresh: bool) -> list[str]:
    import akshare as ak
    RAW.mkdir(parents=True, exist_ok=True)
    failed = []
    for c in companies():
        path = RAW / f"{c['code']}.csv"
        if path.exists() and not refresh:
            continue
        for attempt in range(3):
            try:
                ak.stock_zygc_em(symbol=em_symbol(c["code"])).to_csv(path, index=False, encoding="utf-8-sig")
                print(f"[ok]   {c['code']} {c['name']}")
                break
            except Exception as error:
                if attempt == 2:
                    failed.append(f"{c['code']} {c['name']}: {type(error).__name__}")
                    print(f"[fail] {c['code']} {c['name']}: {type(error).__name__}: {str(error)[:80]}")
                time.sleep(3 * (attempt + 1))
        time.sleep(1.2)
    return failed


def build_tables() -> None:
    names = {p["product_id"]: p["name"] for p in products()}
    rows, unmapped = [], []
    with (ROOT / "data" / "reference" / "downstream_users.csv").open(encoding="utf-8-sig", newline="") as f:
        users = {r["security_code"]: r for r in csv.DictReader(f)}
    with (ROOT / "data" / "reference" / "product_sector_links.csv").open(encoding="utf-8-sig", newline="") as f:
        links = list(csv.DictReader(f))
    for c in companies():
        if c["tier"] == "end_user":
            # End users sell cars, ships …; their exposure is on the input side: the steel products their
            # sector consumes. C-grade (industry knowledge) until a quote from their own annual report that
            # steel is a main raw material is filled in downstream_users.csv, then B-grade.
            u = users[c["code"]]
            for link in (l for l in links if l["sector_id"] == u["sector_id"]):
                rows.append({"security_code": c["code"], "security_name": c["name"], "tier": "end_user", "segment": c["segment"],
                             "period": "", "available_by": "", "basis": "消耗（下游用钢）", "product_id": link["product_id"],
                             "product": names[link["product_id"]], "revenue_share": "", "gross_margin": "",
                             "items": u["steel_input_evidence"], "unmapped_share": "",
                             "grade": "B" if u["steel_input_evidence"] else "C",
                             "source": u["evidence_source"] or link["basis"]})
            continue
        path = RAW / f"{c['code']}.csv"
        if not path.exists():
            unmapped.append({**c, "reason": "未获取到主营构成"})
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            comp = list(csv.DictReader(f))
        periods = exposures_by_period(comp)
        if not periods:
            unmapped.append({**c, "reason": "年报分产品/分行业中没有可识别的产品（如只写“销售商品”）"})
            continue
        for e in periods:
            for pid, v in sorted(e["products"].items(), key=lambda kv: -kv[1]["share"]):
                rows.append({"security_code": c["code"], "security_name": c["name"], "tier": c["tier"], "segment": c["segment"],
                             "period": e["period"], "available_by": e["available_by"], "basis": e["basis"], "product_id": pid,
                             "product": names[pid], "revenue_share": v["share"], "gross_margin": "" if v["gross_margin"] is None else v["gross_margin"],
                             "items": "、".join(v["items"]), "unmapped_share": e["unmapped_share"], "grade": "B",
                             "source": f"东方财富 主营构成（公司定期报告披露）{e['period']} {e['basis']}"})
    EXP.mkdir(parents=True, exist_ok=True)
    with (EXP / "product_exposure.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with (EXP / "unmapped.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "name", "tier", "segment", "reason"], lineterminator="\n")
        w.writeheader()
        w.writerows(unmapped)
    covered = {r["security_code"] for r in rows}
    print(f"\nexposure rows {len(rows)}; companies covered {len(covered)}/{len(companies())}; unmapped {len(unmapped)}")
    for u in unmapped:
        print(f"  - {u['code']} {u['name']}（{u['tier']}）：{u['reason']}")


def fetch_prices() -> None:
    import akshare as ak
    PRICES.mkdir(parents=True, exist_ok=True)
    for p in products():
        symbol = p["price_symbol"]
        if not symbol:
            continue
        try:
            df = ak.futures_zh_daily_sina(symbol=symbol)
            df.to_csv(PRICES / f"{symbol}.csv", index=False, encoding="utf-8-sig")
            print(f"[price] {symbol} {p['name']}: {df['date'].iloc[-1]} 收盘 {df['close'].iloc[-1]}")
        except Exception as error:
            print(f"[price fail] {symbol} {p['name']}: {type(error).__name__}")
        time.sleep(1.0)


if __name__ == "__main__":
    if "--prices" not in sys.argv:
        fetch_composition("--refresh" in sys.argv)
        build_tables()
    fetch_prices()
