# Guarantee test evaluation (independent)

- Date: 2026-09-24
- System: guarantee prompt v3 + normalizer, commit `fbb7d33` (dev freeze)
- Gold: `data/gold/guarantee_test`, guarantee-test-gold-v1, frozen at commit `d76a3c3`
  before the first run (6 documents, 11 events, 5 core steel mills disjoint from
  development and from the reserved final-test mills)
- Runs: 3 (model temperature 0), `outputs/guarantee_test_r1..r3`

## Results

| Run | Event TP/FP/FN | Event F1 | Document fields | Event attributes | Factual attributes |
| --- | --- | --- | --- | --- | --- |
| r1 | 11/1/0 | 95.65% | 67/72 | 149/154 | 216/226 (95.58%) |
| r2 | 11/1/0 | 95.65% | 67/72 | 149/154 | 216/226 (95.58%) |
| r3 | 11/1/0 | 95.65% | 65/72 | 152/154 | 217/226 (96.02%) |

**Reported result: event F1 95.65% (all 3 runs); factual attribute accuracy 95.58–96.02%.**
Recall 100% (every Gold guarantee found in every run); 5 of 6 documents `success`,
1 `needs_review` in every run.

## Error analysis (same in all runs unless noted)

| Doc | Error | Type |
| --- | --- | --- |
| 006 凌钢 | Extra `guarantee_limit` for the 20.94亿 Q2 plan quoted in an **实施公告** | System error: prior-quota rule only recognises 进展公告 titles |
| 006 凌钢 | Debt ratio 67.51 cleared | System error known before the run (“资产负债率（%） 67.51” not recognised) |
| 001 华菱 | External balance 0 cleared | System error known before the run (“对合并报表外单位未提供担保” not recognised) |
| 001 华菱 | 华菱连轧管 relationship `sister_company` | Model error (it is an indirect subsidiary) |
| 001 华菱 | Net-asset ratio 40.00 filled (and in r3 the 222.79亿 quota as total) | Quota vs balance ambiguity; the quota check misses it because the same number also appears after “实际担保余额不超过” |
| 003 安阳 | 11,000万元 related-party guarantee put in external balance | Gold judgment (not labelled 合并报表外); defensible alternative |
| 003 安阳 | 15,000万元 instead of 1.5亿元; page 4 instead of 1 (r1, r2) | Equal value / both pages valid — listed Gold alternatives; strict scoring |

Of the 10 non-narrative mismatches in r1: 2 model or rule errors, 2 known
normaliser defects, 6 Gold-alternative / ambiguous-definition cases.

## Limitations

- 6 documents, 11 events, one annotator without second review.
- `guarantee_released` and `guarantee_overdue` are not covered by this test set.
- Strict scoring treats equal amounts in different units (1.5亿元 vs 15,000万元)
  as wrong; a value-equivalent metric would report higher accuracy.

## After this test (the set is now development data)

Planned for guarantee v4, to be validated only on a new independent set:
treat 实施公告 like 进展公告 for prior-quota events; accept “未提供担保” as
zero external balance; accept “资产负债率（%） 67.51” table form; add a
value-equivalent amount metric to the evaluator (strict metric kept).
