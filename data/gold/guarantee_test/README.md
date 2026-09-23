# Guarantee test Gold (guarantee-test-gold-v1)

## Status

- Version: `guarantee-test-gold-v1`, FROZEN 2026-09-24 (`gold_manifest.lock`).
- System under test: guarantee prompt v3 + normalizer at commit `fbb7d33`,
  committed **before** these documents were selected or opened. No guarantee
  prediction has been run on them.
- Annotator: one annotator, drafted from the source PDFs only; no second review.
- Selection: titles found by web search (CNINFO unreachable from the user's
  network), 5 core steel mills that are neither in the reserved final-test set
  nor in the guarantee development set; at most 2 documents per issuer.
  `guarantee_test_004` (安阳钢铁 2025-119) failed to download, was never opened
  and was dropped.

## Scope

| File | Issuer | Pattern | Events |
| --- | --- | --- | --- |
| 001 | 华菱钢铁 000932 | 2026 annual quota table, 4 subsidiaries, amounts in 亿元 | 4 limit |
| 002 | 三钢闽光 002110 | 2026 annual quota table, 3 subsidiaries, 万元 | 3 limit |
| 003 | 安阳钢铁 600569 | Progress announcement, finance-lease guarantee, creditor = leasing company | 1 provided |
| 005 | 酒钢宏兴 600307 | Board-approved guarantee for a subsidiary, no contract mentioned | 1 limit |
| 006 | 凌钢股份 600231 | Signed guarantee for the controlling shareholder (related party), counter-guarantee | 1 provided |
| 007 | 酒钢宏兴 600307 | Guarantee on the exposure part (1亿) of a 4.5亿 facility | 1 limit |

6 documents, 11 events (8 limit, 3 provided). No `guarantee_released` or
`guarantee_overdue` announcement could be found for these mills: those two
event types are **not tested** here.

## Material judgments (frozen as drafted)

| File | Label | Alternative |
| --- | --- | --- |
| 001 | Amount = 本次新增担保额度 column (65.39/99.60/52.96/4.84 亿元), not the balance column. | — |
| 001 | 华菱连轧管 is 华菱钢管's wholly owned subsidiary → `controlled_subsidiary` from the listed company's view (85.91% indirect). | `wholly_owned_subsidiary`. |
| 001 | 是否关联担保 “否” → `is_related_transaction = false`. | null (text does not say 不构成关联交易). |
| 001 | `guarantee_type` null: 保证、抵押、质押等 not one type. | `joint_and_several`. |
| 001 | Total null: 222.79亿 is a quota (担保额度总金额), not a balance. External = 0 亿元 from “对合并报表外单位未提供担保”. | total = 222.79亿元, ratio 40.00. |
| 002 | Total = 实际发生对外担保余额 61,205.99万元 (3.16%); 212,967.48万元 is an approved quota. | total = 212,967.48. |
| 003 | `guarantee_provided`: “本次担保发生后…新增担保额度为1.5亿元” says the guarantee has occurred, although signing is not stated. | `guarantee_limit`. |
| 003 | Amount 1.5 亿元 (summary and overview); the agreement section prints the same value as 15,000 万元. | 15,000 万元. |
| 005, 007 | Board approval, no signed contract → `guarantee_limit` (prompt v3 rule 7). | `guarantee_provided`. |
| 005, 007 | Total = 累计为全资子公司提供担保余额 (9.49 / 7.71 亿元); external null because a counter-guarantee to the controlling shareholder exists but is not quantified. | external = 0. |
| 006 | “凌钢集团与本公司之间构成关联关系” → `is_related_transaction = true`. | null. |
| 006 | Total = 累计对外担保余额 27.37亿元 (33.60%); 77亿 is 担保总额. External null (25.86亿 to the controlling shareholder is not labelled 合并报表外). | total = 77亿元 / 94.53. |
| 006 | Debt ratio 67.51 from the table row “资产负债率（%） 67.51”. | — |
| all | Overdue = 0 with the unit of the cumulative paragraph. | 元. |

## Known before the run (not fixed: the system is frozen)

Replaying this Gold through the frozen normalizer shows two values it cannot
keep; they are expected errors of the system under test and will be fixed only
in a later version, after this test has been run:

1. 001: “对合并报表外单位**未提供**担保” is not in the zero-external-balance
   pattern (which expects 无对外担保 / 余额为0), so a correct 0 is cleared.
2. 006: the debt-ratio check expects “67.51%”; a table header “资产负债率（%）”
   before the number is not recognised, so a correct 67.51 is cleared.
