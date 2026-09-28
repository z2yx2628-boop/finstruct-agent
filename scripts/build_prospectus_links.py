"""Clean the extractor's candidates into data/reference/prospectus_links.csv (reproducible version of the
first manual cleaning). Keeps supplier / customer / receivable / payable / prepayment / contract-liability rows
with a real counterparty name; drops anonymised rows, header fragments and 'other receivables'.
    python scripts/extract_prospectus_counterparties.py
    python scripts/build_prospectus_links.py
    python scripts/check_prospectus_links.py
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAND = ROOT / "data" / "reference" / "prospectus_counterparties_candidates.csv"
OUT = ROOT / "data" / "reference" / "prospectus_links.csv"
DOCS = {  # file -> (issuer, issuer_id: listed code for company-level documents, group id for group documents, title)
    "1221258295.PDF.pdf": ("河钢股份", "000709", "河钢股份有限公司2024年面向专业投资者公开发行可续期公司债券（第四期）募集说明书摘要"),
    "hbis_2025_03.pdf": ("河钢股份", "000709", "河钢股份有限公司2025年面向专业投资者公开发行可续期公司债券（第一期）募集说明书摘要"),
    "hbis_group_2023_12.pdf": ("河钢集团", "G_HBIS", "河钢集团有限公司2023年面向专业投资者公开发行低碳转型挂钩公司债券（第四期）募集说明书"),
    "hbis_group_2023_12_summary.pdf": ("河钢集团", "G_HBIS", "河钢集团有限公司2023年科技创新公司债券（第六期）募集说明书摘要"),
    "ansteel_group_2025_mtn2.pdf": ("鞍钢集团", "G_ANSTEEL", "鞍钢集团有限公司2025年度第二期中期票据募集说明书"),
    "baotou_group_2025_07.pdf": ("包钢集团", "G_BAOTOU", "包头钢铁（集团）有限责任公司2025年度第三期科技创新债券基础募集说明书"),
    "shagang_2024_03.pdf": ("沙钢集团", "G_SHAGANG", "江苏沙钢集团有限公司2024年度第一期超短期融资券（科创票据）募集说明书"),
    "baosteel_2024_scp2.pdf": ("宝钢股份", "600019", "宝山钢铁股份有限公司2024年度第二期超短期融资券募集说明书"),
    "hangang_group_2026_06.pdf": ("杭钢集团", "G_HANGGANG", "杭州钢铁集团有限公司2026年度第一期超短期融资券募集说明书"),
    "nangang_2023_08.pdf": ("南京南钢钢铁联合", "600282", "南京南钢钢铁联合有限公司2023年度第一期超短期融资券募集说明书（南钢股份控股股东）"),
    "tisco_2024_mtn1.pdf": ("太钢不锈", "000825", "山西太钢不锈钢股份有限公司2024年度第一期中期票据募集说明书"),
}
ROLES = ("supplier", "customer", "receivable", "payable", "prepayment", "contract_liability")
HEADER = re.compile(r"(?:百分比|比例|种类|款项总余?|项合计的|单位名称|供应商名称|客户名称|债务人名称|与本公司关系|与发行人关系|"
                    r"未偿还原因|与本公司的关系|是否关联方?)")
PREFIX = re.compile(r"^(占[一-龥]{0,10}的?|与本公司未偿还原因|与本公司关系|与发行人关系|与本公司的关系|采购数量|"
                    r"公司简称销量（吨）|应收账款?|其他应收款项合|预付对象|单位名称|客户名称|供应商名称|债务人名称|名称)")
SUFFIX = re.compile(r"(未到账期|未到交货期|一年以内|三年以上|货款|资产使用费|土地补偿款|转让土地款|土地转让款|往来款)$")
BAD = re.compile(r"占比|板块|品种|合计|金额|数量|比例|单位\s*\d|客户\s*\d|^[A-E]$|未结转|与本公司|平均价格|产品$")
FIX = {"其他应收款项合北台钢铁（集团）有限责": None, "天津鞍钢天铁冷轧薄板有": None,
       "宝鸡石油钢管有限责任公司西安石": "宝鸡石油钢管有限责任公司西安石油专用管分公司",
       "油专用管分公司宁波科田磁业股份有限公司": "宁波科田磁业股份有限公司", "中铁大桥局集团物资有限公": "中铁大桥局集团物资有限公司",
       "中铁大桥局集团物资": "中铁大桥局集团物资有限公司", "中铁四局集团有限公司钢结": "中铁四局集团有限公司钢结构建筑分公司",
       "中铁四局集团有限公": "中铁四局集团有限公司钢结构建筑分公司", "有限公司中铁四局集团有限公": "中铁四局集团有限公司钢结构建筑分公司",
       "构建筑分公司": None, "司钢结构建筑分公司沙桐（泰兴）化学有": "沙桐（泰兴）化学有限公司", "武汉航科物流有限公": "武汉航科物流有限公司",
       "宁波梅山保税港区锦程沙洲股权": "宁波梅山保税港区锦程沙洲股权投资有限公司", "投资有限公司安徽白帝集团有限公司": "安徽白帝集团有限公司"}
COKE = {"中国平煤神马集团焦化销售有限公司", "临涣焦化股份有限公司", "山西阳光焦化集团股份有限公司", "山西焦化股份有限公司"}
ORE = {"HopeDownsMarketingCompanyPtyLtd"}
COAL = {"淮北矿业股份有限公司", "平顶山天安煤业股份有限公司", "山东能源集团煤炭营销有限公司", "黑龙江龙煤矿业集团股份有限公司", "安徽省皖煤国贸有限责任公司", "山西焦煤集团有限责任公司", "山西焦煤集团煤焦销售有限公司",
        "焦作国龙物流有限公司", "山西焦煤能源集团股份有限公司", "开滦（集团）有限责任公司", "哈尔滨嘉运煤焦供应链有限公司", "贵州盘江精煤股份有限公司"}
LISTED = {"淮北矿业股份有限公司": "600985", "平顶山天安煤业股份有限公司": "601666", "山西焦化股份有限公司": "600740", "贵州盘江精煤股份有限公司": "600395", "山西焦煤能源集团股份有限公司": "000983", "宁波美的联合物资供应有限公司": "000333",
          "安徽鸿路钢结构（集团）股份有限公司": "002541", "中信金属股份有限公司": "601061"}
NOTES = {"华晨汽车集团控股有限公司": "坏账准备 28,676.69 万元（约 93%）；华晨集团 2020 年进入破产重整",
         "天津物产集团财务有限公司": "坏账准备 40,295.83 万元（约 56%）；天津物产集团 2021 年进入破产重整",
         "宁波美的联合物资供应有限公司": "美的集团（000333）的采购平台", "山西焦煤集团有限责任公司": "山西焦煤（000983）的控股股东",
         "山西焦煤集团煤焦销售有限公司": "山西焦煤集团下属销售公司"}


def product_of(kind: str, name: str) -> str:
    if kind not in ("supplier", "payable", "prepayment"):
        return ""
    return "P_COKE" if name in COKE else "P_IRON_ORE" if name in ORE else "P_COKING_COAL" if name in COAL else ""


def basis_of(issuer: str, kind: str, name: str) -> str:
    if not product_of(kind, name):
        return ""
    if issuer == "鞍钢集团" and kind == "supplier":
        return "原表标题“焦煤前五大供应商”"
    if issuer == "南京南钢钢铁联合" and kind == "supplier":
        return "原表“采购商品种类”列（煤焦/矿）"
    return "按对方主营判断，原表未写品种"


def clean(name: str) -> str | None:
    n = name.strip()
    if n in FIX:
        return FIX[n]
    n = HEADER.split(n)[-1].strip()           # header words glued in front of the first row
    n = re.sub(r"^[A-Za-z]{2,6}\)", "", n)    # tail of a wrapped English name, e.g. "anch)"
    for _ in range(2):
        n = PREFIX.sub("", n).strip()
        n = SUFFIX.sub("", n).strip()
    n = FIX.get(n, n)
    if n and re.match(r"^(份|业|司|限|（|事业|能源有限公司$|有限公司)", n):
        return None                             # a wrapped name whose first half is on the line above
    if not n or len(n) < 4 or BAD.search(n) or not re.search(r"(公司|集团|局|中心|会社|委员会|总厂|Ltd|LIMITED|Limited|AG|Inc|IBM|Kyndryl|Services|INDUSTRIES|国际)$", n):
        return None
    return n


def period_of(title: str) -> str:
    m = re.search(r"(20\d\d)\s*年(?:度|末)?\s*(?:(?:\d{1,2}\s*-\s*)?(\d{1,2})\s*月)?", title)
    if not m:
        return ""
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m.group(2) else f"{m.group(1)}-12"


def main() -> None:
    rows, seen = [], set()
    with CAND.open(encoding="utf-8-sig", newline="") as f:
        for x in csv.DictReader(f):
            if x["file"] not in DOCS or x["kind"] not in ROLES:
                continue
            if "其他应收" in x["table"] or "其他应付" in x["table"]:
                continue
            name = clean(x["counterparty"])
            if not name:
                continue
            issuer, issuer_id, title = DOCS[x["file"]]
            period = period_of(x["table"]) or ("2023-12" if issuer == "河钢股份" else "")
            unit, note = x["unit"], ""
            if "销量" in x["table"] or (x["file"].startswith("hbis_group") and x["kind"] == "customer"):
                unit, note = "吨", "表中为销量（吨），不是金额"
            key = (issuer_id, x["kind"], name, period)
            if key in seen or not period:
                continue
            seen.add(key)
            rows.append({"issuer": issuer, "issuer_id": issuer_id, "role": x["kind"], "counterparty": name,
                         "counterparty_code": LISTED.get(name, ""), "amount": x["amount"], "unit": unit, "period": period,
                         "related_party": x["related_party"] or "未注明", "source_file": x["file"], "source_title": title,
                         "page": x["page"], "note": "；".join(v for v in (note, NOTES.get(name, "")) if v),
                         "verified": "N", "product_id": product_of(x["kind"], name),
                         "product_basis": basis_of(issuer, x["kind"], name)})
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    from collections import Counter
    print(len(rows), "rows;", dict(Counter(r["issuer"] for r in rows)))


if __name__ == "__main__":
    main()
