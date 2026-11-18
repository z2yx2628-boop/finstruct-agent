"""Read the per-counterparty appendix of Baosteel's annual related-transaction estimate (rules, no model).

Baosteel's announcement gives only category totals in its body (page 3); the counterparties are in
附件 2 "与同一关联人……预计情况表" (short names such as 马钢集团, 宝武资源). The frozen extraction system
and the Gold annotation both cover the body table only, so Baosteel had almost no related-party edges.
This script reads the appendix line by line with fixed rules and writes a document in the same schema
(schemas/related_party.py) to outputs/manual_freeze/related_party/, which the live graph build reads.

Each row keeps its page and the original line as evidence; rows with a 2026 estimate of 0 are left out.
Short names are mapped to the full names listed in section 三 of the same announcement (NAMES below).

    python scripts/parse_related_appendix.py            # needs pdftotext (poppler) on PATH
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "data" / "raw" / "related_dev" / "related_dev_001_600019_annual_estimate.pdf"
OUT = ROOT / "outputs" / "manual_freeze" / "related_party" / "related_dev_001_600019_annual_estimate.json"
GOLD = ROOT / "data" / "gold" / "related_dev" / "related_dev_001_600019_annual_estimate.json"   # header fields only

# short name in the appendix -> full name in section 三 (主要关联方关联关系和基本情况) of the same announcement
NAMES = {
    "宝武集团": "中国宝武钢铁集团有限公司", "欧冶云商": "欧冶云商股份有限公司", "宝钢不锈": "上海宝钢不锈钢有限公司",
    "宝钢金属": "宝钢金属有限公司", "宝武资源": "宝武资源有限公司", "八一钢铁": "新疆八一钢铁集团有限公司",
    "中南钢铁": "宝武集团中南钢铁有限公司", "宝钢特钢": "宝钢特钢有限公司", "宝钢德盛": "宝钢德盛不锈钢有限公司",
    "华宝投资": "华宝投资有限公司", "华宝信托": "华宝信托有限责任公司", "武钢集团": "武钢集团有限公司",
    "宝武环科": "宝武集团环境资源科技有限公司", "宝钢心越": "上海宝钢心越人才科技有限公司",
    "马钢集团": "马钢（集团）控股有限公司", "宝地不动产": "上海宝地不动产资产管理有限公司", "宝武铝业": "宝武铝业科技有限公司",
    "宝武水务": "宝武水务科技有限公司", "宝武清能": "宝武清洁能源有限公司", "宝武装备": "宝武装备智能科技有限公司",
    "宝武原料": "宝武原料供应有限公司", "欧冶工业品": "欧冶工业品股份有限公司", "太原钢铁": "太原钢铁（集团）有限公司",
    "重庆长寿": "重庆长寿钢铁有限公司", "新余集团": "新余钢铁集团有限公司", "中国中钢": "中国中钢集团有限公司",
    "宝钢包装": "上海宝钢包装股份有限公司", "宝武共享": "宝武共享服务有限公司", "宝武物流": "宝武物流资产有限公司",
    "化工宝数科": "上海化工宝数字科技有限公司", "武钢轧辊": "武汉钢铁集团轧辊有限责任公司", "山钢集团": "山东钢铁集团有限公司",
    "西藏矿业": "西藏矿业资产经营有限公司", "宝武产教": "宝武产教融合发展（上海）有限公司",
    "重钢集团": "重庆钢铁（集团）有限责任公司", "财务公司": "宝武集团财务有限责任公司",
    "华宝基金": "华宝（上海）股权投资基金管理有限公司",
}
# section 三 1: 宝武集团 is the parent; 山钢集团 is related through a former officer; all others are controlled by 宝武集团
RELATION = {"宝武集团": "parent_or_controlling_shareholder", "山钢集团": "other_related_party"}
SECTIONS = [("一、采购商品", "purchase_goods", "采购商品"), ("二、销售产品", "sell_goods", "销售产品、商品"),
            ("三、接受劳务", "receive_services", "接受劳务"), ("四、提供劳务", "provide_services", "提供劳务"),
            ("1、租入资产", "lease_in", "租入资产"), ("2、租出资产", "lease_out", "租出资产")]
ROW = re.compile(r"^\s*(\S+?)\s+(市场价|协议价)\s+([\d,]+\.\d+)\s+[\d.]+%\s+([\d,]+\.\d+)\s+[\d.]+%")
NUM = lambda s: float(s.replace(",", ""))


def main() -> None:
    text = subprocess.run(["pdftotext", "-layout", str(PDF), "-"], capture_output=True, text=True, check=True).stdout
    pages = text.split("\f")
    start = next(i for i, p in enumerate(pages) if "附件 2" in p and "预计情况表" in p)
    head = json.loads(GOLD.read_text(encoding="utf-8"))
    company = head["company_name"]
    rows, section, unknown, zero = [], None, [], 0
    for pno in range(start, len(pages)):
        for line in pages[pno].splitlines():
            for key, cat, label in SECTIONS:
                if line.strip().startswith(key):
                    section = (cat, label)
            m = ROW.match(line)
            if not m or not section:
                continue
            short, est, prior = m.group(1), NUM(m.group(3)), NUM(m.group(4))
            if short == "其他":
                continue
            if short not in NAMES:
                unknown.append(short)
                continue
            if est == 0:
                zero += 1
                continue
            rows.append({"listed_company": company, "counterparty": NAMES[short],
                         "relationship": RELATION.get(short, "sister_company"),
                         "transaction_category": section[0], "category_text": section[1], "goods_or_services": None,
                         "estimated_amount": est, "estimated_unit": "百万元",
                         "prior_year_actual_amount": prior, "prior_year_actual_unit": "百万元", "currency": "CNY",
                         "source_page": pno + 1, "evidence_text": re.sub(r"\s+", " ", line.strip()), "confidence": 1.0})
    if unknown:
        sys.exit(f"short names without a full name: {sorted(set(unknown))}")
    doc = {k: head[k] for k in ("security_code", "security_name", "company_name", "announcement_number",
                                "announcement_date", "estimate_year", "total_estimated_amount", "total_estimated_unit",
                                "requires_shareholder_approval")}
    doc["transactions"] = rows
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    by = {}
    for r in rows:
        by[r["transaction_category"]] = by.get(r["transaction_category"], 0) + r["estimated_amount"]
    print(f"{len(rows)} rows ({zero} zero-estimate rows left out) -> {OUT.relative_to(ROOT)}")
    print({k: round(v, 2) for k, v in by.items()})


if __name__ == "__main__":
    main()
