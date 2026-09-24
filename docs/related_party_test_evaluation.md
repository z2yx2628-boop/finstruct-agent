# Related-party (日常关联交易) test evaluation (independent)

- Date: 2026-09-24
- System: related-party prompt v1 + normalizer, commit `832efb8` (dev freeze)
- Gold: `data/gold/related_test`, related-test-gold-v1, frozen at commit `d05d3d3`
  before the first run (4 documents, 153 records; issuers 华菱钢铁, 八一钢铁,
  酒钢宏兴 — disjoint from development and from the reserved final-test mills)
- Runs: 3 (temperature 0). r3 first failed on an API connection error and was re-run.
- Evaluator: two-pass pairing (commit after `d05d3d3`, see below)

## Results

| Run | Record TP/FP/FN | Record F1 | Document fields | Factual attributes |
| --- | --- | --- | --- | --- |
| r1 | 151/2/2 | 98.69% | 36/36 | 1410/1546 (91.20%) |
| r2 | 151/2/2 | 98.69% | 36/36 | 1410/1546 (91.20%) |
| r3 | 151/2/2 | 98.69% | 36/36 | 1410/1546 (91.20%) |

**Reported result: record F1 98.69% (all 3 runs); factual attribute accuracy 91.20%;
document fields 100%.** Tables of up to 64 rows (华菱) were extracted without truncation.

### Evaluator change after the first run (disclosed)

The first-run report printed factual accuracy 89.33%. Two 华菱 rows were
misclassified (工程建设 → purchase_goods, a real error), and the greedy pairing then
paired later Gold rows with their neighbours' predictions, counting 8 correctly
extracted rows as wrong counterparty/amount. Pairing now first locks exact matches
(same category, counterparty and amount), then pairs the rest greedily. The model
outputs were not changed; record F1 is unchanged; both numbers are reported here.

## Error analysis (r1; identical pattern in r2, r3)

| Errors | Where | Cause | Type |
| --- | --- | --- | --- |
| 2 FP + 2 FN | 001 华菱 | 工程建设 rows (湘钢集团, 涟钢建设) classified as purchase_goods instead of receive_services | Model error (category) |
| 64 source_page | mostly 001 华菱 (51) | Rows on pages 2–3 reported one page too early | Model error (page only; values correct) |
| 9 records × amount/unit/currency (44 fields) | 002 八一, page 7 | Normalizer cleared correct amounts: the unit declaration is pages away and the 差异原因 column contains “。”, which ends the long-table unit rule | System defect (normalizer) |
| 26 relationship | 002 八一 (25), 004 | “八钢公司及子公司”, “宝武集团及子公司” read as sister_company (Gold: parent); group associates as associate_or_joint_venture (Gold: other_related_party) | Gold-alternative / ambiguous definition |
| 1 counterparty | 003 八一 borrowing | wording of the lender group | Minor |
| 2 prior-year | 004 酒钢 | 钢铁技术学院 row with only one printed number | Minor |

Without the normalizer defect and the relationship ambiguity, factual accuracy
would be about 96%; this is an explanation, not a reported number.

## Limitations

- 4 documents from 3 issuers; one annotator; tables verified against printed subtotals.
- Appendix per-counterparty tables (e.g. 宝钢 附件2) and finance-company deposit/loan
  tables are out of scope by design.
- Relationship labels depend on how a group row (“X及子公司”) is read; the definition
  should be fixed in the annotation guideline before the next test.

## After this test (the set is now development data)

Planned for related-party v2, to be validated only on a new independent set:
unit rule that is not cut by sentence ends inside table cells (page-level
table detection); explicit rule for group rows (“X及子公司” → parent vs sister);
工程建设/综合服务费 → receive_services example in the prompt.
