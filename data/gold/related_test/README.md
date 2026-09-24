# Related-party test Gold (related-test-gold-v1)

## Status

- Version `related-test-gold-v1`, frozen by `gold_manifest.lock` before the first run.
- System under test: related-party prompt v1 + normalizer at commit `832efb8`
  (committed before these documents were selected or opened).
- One annotator, from the source PDFs only; no second review. Every table was
  cross-checked against its printed 小计/合计 (within ±2 万元 rounding).
- Issuers (华菱钢铁, 八一钢铁, 酒钢宏兴) are disjoint from the development set
  and from the reserved final-test mills.
- 001 was first downloaded from a Securities Times e-paper PDF that bundled
  several other announcements; it was replaced with the standalone Sina copy
  of the same announcement (2026-3) before annotation.

## Scope

| File | Issuer | Pattern | Records |
| --- | --- | --- | --- |
| 001 | 华菱钢铁 000932 | Counterparty × content, purchase and sales tables + two financial tables; merged counterparty cells | 64 |
| 002 | 八一钢铁 600581 | Counterparty cells carry the goods in brackets, e.g. “八钢公司之子公司（铁矿石）”; separate 2025 table precedes the 2026 table | 44 |
| 003 | 八一钢铁 600581 | Related-party **borrowing budget** (42亿元 from 八钢公司及其下属子公司), not a trading table | 1 |
| 004 | 酒钢宏兴 600307 | Category 采购/销售 × counterparty; **2025 actual column comes before the 2026 estimate column** | 44 |

153 records in total.

## Material judgments

| File | Label | Alternative |
| --- | --- | --- |
| 001 | Row content decides the category: 原辅料/动力介质 → purchase_goods; 综合服务费/工程建设/接受劳务 → receive_services; 租赁 in the purchase table → lease_in, in the sales table → lease_out; 钢材/代购物资/废弃物/钢水/钢坯/钢管/动力介质 in the sales table → sell_goods | 工程建设 as other |
| 001 | Counterparties are subsidiaries of the controlling shareholder (“关联方主要是公司控股股东湖南钢铁集团及其直接或间接控制的法人”) → sister_company; “湖南钢铁集团及下属子公司” → parent | — |
| 001 | Total = 2,937,117 万元 from the overview sentence (no grand-total row) | null |
| 002 | Counterparty kept verbatim including the bracketed goods; bracket width as printed | counterparty without the bracket |
| 002 | 房产土地租赁 / 租赁 rows sit in the 接受劳务 block → receive_services (table category wins, rule 12) | lease_in |
| 002 | “X之子公司” → sister_company; “X及子公司”/X → parent (宝武集团 is the actual controller, 八钢公司 the controlling shareholder); “X之联营企业” → other_related_party; “本公司之联营企业” → associate_or_joint_venture | other_related_party for group-level rows |
| 002 | 财务公司 business (28亿元 in 2.金融业务与服务) out of scope | — |
| 003 | One financial_services record, 42 亿元, page 2 | zero records (a loan budget is not a daily trading estimate) |
| 004 | 钢铁技术学院 purchase row prints only 150 → 2026 estimate 150, prior-year null (checked against 采购合计) | — |
| 004 | No grand total (only 采购合计 and 销售合计) → total null; no shareholder-approval statement → null | total = sum |
| 004 | 财务公司 deposits/loans and 担保费用 tables out of scope | — |
