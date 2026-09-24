# Related-party development Gold (related-dev-gold-v2)

- Development set (not a test set); drafted 2026-09-24 from source PDFs before any
  related-party prediction was run. One annotator.
- Sources: `data/manifests/related_dev_sources.csv`.

| File | Issuer | Pattern | Records |
| --- | --- | --- | --- |
| 001 | 宝钢股份 600019 | Estimate table by **category only** (no counterparty column), 百万元; per-party breakdown only in 附件2 (out of scope); separate 财务公司 table (out of scope) | 6 |
| 002 | 首钢股份 000959 | Counterparty × category table with 小计/合计 rows, two tables (采购 / 销售), 万元, prior column = 2025年1-10月 | 25 |
| 003 | 柳钢股份 601003 | **Hard negative**: shareholder-meeting resolution approving the estimate; no table | 0 |

## Scope rules (prompt v1)

- Records come only from the main-body current-year estimate table; appendix
  per-party tables, financial-company deposit/loan tables and entrusted asset
  management are out of scope.
- Category-only tables → `counterparty = null`, `relationship = null`.
- 小计 / 合计 / 关联采购合计 / 日常关联交易总金额 rows are not records; the grand
  total goes to `total_estimated_amount`.
- `prior_year_actual_amount` = the actual column of the same row even when it is
  partial-year (002: 2025年1-10月).
- 资金使用费 / 利息收入 rows inside the estimate table → `financial_services`.

## Material judgments

| File | Label | Alternative |
| --- | --- | --- |
| 001 | total = 133,175 百万元 (合计 row) | 1331.75 亿元 (same value, body text) |
| 001 | `requires_shareholder_approval = true` (“达到股东会审议标准的关联交易需提交股东会审议”) | null (only part of it) |
| 002 | Counterparty “首钢集团有限公司及下属企业” as printed; relationship parent (控股股东) | — |
| 002 | 迁安中化, 西山焦化, 盾石, 青岛钢业, 京海航运, 浙金钢材 are 参股公司 of the company or its subsidiaries → `associate_or_joint_venture`; “其他关联方” = 联营、合营企业 per the table note | `other_related_party` |
| 002 | 首钢(青岛)钢业 采购商品 2026 estimate 0 kept as a record (0 is printed) | drop zero rows |
| 003 | `estimate_year` 2025 (v2; v1 had null): the motion title names the 2025 estimate | null |

## System change made while drafting

The sales-table rows of 002 are more than 400 characters below “单位：万元”, so
the shared amount check rejected every one of them. The related-party normalizer
now also accepts a number when the nearest preceding unit declaration names the
unit and no sentence end (。) lies in between.

## Revision log

| Version | Change | Why |
| --- | --- | --- |
| v1 | Initial draft (31 records) | — |
| v2 | 003 `estimate_year` null → 2025 | Dev run 1: the model read the year from the motion title “…2025年度日常关联交易预计的议案”, which is explicit text; v1 was too strict. |

Dev run 1 (prompt v1, Gold v1): record F1 92.54% (TP/FP/FN 31/5/0), factual 98.22%.
Errors: 5 extra `financial_services` rows from 宝钢's separate 财务公司 deposit/loan
table (out of scope) → normalizer now drops financial-service rows whose
counterparty is a finance company; 5 wrong source pages on 首钢 page-3 rows
(model error, kept); 003 year (Gold revised above).
