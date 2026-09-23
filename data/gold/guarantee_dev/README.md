# Guarantee development Gold (guarantee-dev-gold-v2)

## Status

- **Development set, not a test set.** These 4 documents are used to tune the
  guarantee prompt and normalizer; scores on them are development results and
  must never be reported as independent accuracy. No lock file on purpose.
- Drafted 2026-09-23 from the source PDFs only, before any guarantee
  prediction was run. One annotator, no second review.
- Sources and SHA-256: `data/manifests/guarantee_sources.csv`.

## Scope

| File | Issuer | Pattern | Events |
| --- | --- | --- | --- |
| 001 | 方大特钢 600507 | 14-row table, 7 subsidiaries × banks, counter-guarantee for 2 | 14 limit |
| 002 | 安泰集团 600408 | Related-party renewal guarantee, overdue 4亿元 | 4 limit |
| 003 | 中信特钢 000708 | Subsidiary guarantees another subsidiary, contract signed | 1 provided |
| 004 | 南钢股份 600282 | USD guarantee for Indonesian subsidiary under annual quota | 1 provided |

## Rules added with this Gold (prompt v1 rules 5 and 27)

- A guarantee table listed per **guaranteed party + creditor** gives one event
  per row, `creditor` = that row's creditor, amount = that row's amount. Rows
  are never summed (the normalizer would reject a summed amount anyway, since
  it does not appear in the source).
- "No overdue guarantee" → `overdue_guarantee_amount = 0` with the unit used by
  the cumulative-guarantee paragraph or table (万元 in 001, 003, 004).

## Material judgments

| File | Label | Alternative |
| --- | --- | --- |
| 001 | Board-approved but contracts not yet signed (“尚未签署担保合同”) → `guarantee_limit` (v2 rule 7). | `guarantee_provided` (v1). |
| 001 | Guaranteed parties use the full names from 重要内容提示, not the table abbreviations. | Abbreviations (悬架集团…). |
| 001 | 方大长力 is “间接全资子公司” → `wholly_owned_subsidiary`; 重庆红岩, 济南重弹 → `controlled_subsidiary`. | — |
| 001 | Counter-guarantee `true` only for 重庆红岩/济南重弹; `null` for the other five (text does not say they have none). | `false` for the other five. |
| 001 | `external_guarantee_balance` null: 405,500 includes mutual guarantees with 方大炭素 and only the within-group 305,500 is split out; the off-group figure would need subtraction. | 100,000 万元. |
| 002 | Amount = 续保金额 column (40,650 / 19,350 / 5,750 / 16,820 万元), not the current balance column. | One event of 8.26亿元. |
| 002 | 新泰钢铁 is 100% held by the controlling shareholder’s company → `sister_company`; “构成关联担保” → `is_related_transaction = true`. | `other_related_party`. |
| 002 | Cumulative 26.11亿元 is to the related party outside the group → `external_guarantee_balance`; `total_guarantee_balance` null (group total not disclosed). | total = 26.11亿元. |
| 003 | Relationship judged against the guarantor (天管国贸 is 天津钢管’s wholly owned subsidiary). | `controlled_subsidiary` (listed company’s view). |
| 003 | Signing date 2025-06-25 is not a guarantee-period date → `start_date` null. | 2025-06-25. |
| 003 | 12,000万元 is an off-group guarantee **quota**, not a balance → `external_guarantee_balance` null. | 12,000 万元. |
| 004 | Party = English legal name as printed in the table; unit `万美元`, currency USD. | Chinese name 印尼金祥新能源科技有限责任公司. |
| 004 | `source_page` = 3 (担保协议的主要内容). | 1 (summary table). |
| all | Debt ratio filled only where printed as a percentage (001); not computed from assets/liabilities (002–004). | — |

## Known system fix made while drafting

Whitespace removal glued table cells ("3,600.00" + next row number "2" →
"3,600.002"), so every table amount in 001/002 failed the evidence check and
was deleted. `compact_keep_number_breaks` in `src/guarantee_normalizer.py` now
keeps a space between two digits. The same bug still exists in the capacity
investment check and is scheduled for a later capacity version.

## Revision log

| Version | Date | Change | Why |
| --- | --- | --- | --- |
| v1 | 2026-09-23 | Initial draft, 20 events. | — |
| v2 | 2026-09-23 | 001 (14) and 002 (4) relabelled `guarantee_provided` → `guarantee_limit`; nothing else changed. | Dev run 1 (prompt v1) exposed that v1 rules 6/7 overlapped: “board-approved specific amount” fell under both. Prompt v2 draws the line at the **signed contract**: signed / actually provided → `provided`; approved but unsigned (“尚未签署”“以实际签订的合同为准”“拟提供”“尚需股东大会审议”) → `limit`. This separates actual liabilities from authorised capacity, which is what the risk graph needs. Changed on a development set only; the v1 labels are kept in git history and the dev-run-1 report scores against v1. |

Dev run 1 (prompt v1, v1 Gold): event F1 28.57%, factual attributes 89.39%.
Main errors: event type on 001 (all 14 rows otherwise correct), an overdue event taken
from the cumulative section (002), a prior annual quota taken as a new limit in a
progress announcement (004), debt ratios computed from assets/liabilities (002–004),
Chinese-numeral signature dates rejected by the date check (002, 004).

Dev run 2 (prompt v2, v2 Gold): event F1 76.47% (TP/FP/FN 13/1/7), factual 81.74%.
- 001: v2 rule 7 said "one limit event per guaranteed party", so the model summed each
  party's bank rows (8,400 / 6,000 / 27,800 / 12,000 万元); the normalizer rejected the
  sums (not in the source) and 7 rows were lost. Prompt v3 makes rule 7 defer to rule 5
  (one event per party+creditor row, never summed) and adds a pre-output check.
- 002: the "不超过8.26亿元" total was emitted next to its four rows -> normalizer now drops
  a creditor-less event whose amount equals the sum of the same party's rows (±0.5%).
- 003/004: a quota (额度总金额) and an inferred 0 were put in `external_guarantee_balance`
  -> normalizer clears a balance introduced only as 额度, and a 0 without an explicit
  "无对外担保 / 对合并报表外担保余额为0".
- Replaying run-2 raw outputs through the new normalizer (no new LLM call): 002-004
  events all correct; 001 still needs the v3 prompt.
