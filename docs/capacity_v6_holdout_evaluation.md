# Capacity V6 holdout evaluation

## Frozen inputs

- System under test: V6, commit `f08347f` (prompt unchanged from V5,
  `prompts/capacity_extraction_v5.txt`)
- Model: `qwen-plus`, `temperature=0`
- Gold: `capacity-v6-holdout-gold-v1`, commit `5381eee` (17:12:33 local);
  first prediction run started 17:12:42 local
- Corpus: 12 documents, 10 Gold events, 4 Gold capacity records, 3
  zero-event documents (2 hard negatives); issuers disjoint from every
  earlier capacity split
- Runs: 3 (`outputs/capacity_v6_holdout_r1..r3`)

No prompt, rule or Gold change was made after the first prediction.

## Official results

| Metric | r1 | r2 | r3 |
| --- | ---: | ---: | ---: |
| Event TP / FP / FN | 10 / 0 / 0 | 10 / 0 / 0 | 10 / 1 / 0 |
| Event F1 | 100.00% | 100.00% | 95.24% |
| Capacity-record TP / FP / FN | 4 / 1 / 0 | 4 / 0 / 0 | 4 / 0 / 0 |
| Capacity-record F1 | 88.89% | 100.00% | 100.00% |
| Document-field accuracy | 60/60 | 60/60 | 60/60 |
| Factual-attribute accuracy | 185/210 (88.10%) | 186/210 (88.57%) | 188/210 (89.52%) |
| Narrative strict accuracy | 1/30 (3.33%) | 1/30 (3.33%) | 1/30 (3.33%) |
| Safe canonical all-attribute accuracy | 186/240 (77.50%) | 187/240 (77.92%) | 189/240 (78.75%) |

Headline: event F1 95.2–100%, capacity-record F1 88.9–100%, factual-attribute
accuracy 88.1–89.5% over three runs.

## Comparison across independent evaluations

| Metric | V4 blind (8 docs, 1 run) | V5 holdout v1 (9 docs, 3 runs) | **V6 holdout (12 docs, 3 runs)** |
| --- | ---: | ---: | ---: |
| Event F1 | 87.5% | 72.7–88.9% | **95.2–100%** |
| Capacity-record F1 | 53.3% | 22.2–23.5% | **88.9–100%** |
| Document-field accuracy | 95.0% | 97.8% | **100%** |
| Factual-attribute accuracy | 80.8% | 78.0–79.3% | **88.1–89.5%** |

Each column is a different document set, so the comparison shows direction,
not a controlled difference. V6 is the first version evaluated on an unseen
set after its rules were frozen, and it did not collapse the way V5 did.

## Error analysis

### Events and capacity records

- r3, 009 河钢资源: one `suspension` event without a project name was emitted
  for the flood-driven mine halt (Gold: zero events). r1 and r2 were correct.
- r1, 002 永兴 upgrade: the 25万吨/年 capacity of a different, earlier project
  mentioned as background was attached to the upgrade event. r2 and r3 were
  correct.
- All three zero-event documents were otherwise correct in every run,
  including both hard negatives (asset bid, data centre).
- The 暂缓实施 announcement (010) was classified as `suspension` in every run.

### Attributes

**Investment deletion in tabular delay announcements (largest remaining
cause).** In all runs the model extracted the correct investment for the
three delay documents (鸿路 8,000万元, 广大 30,000万元, 盛德 262,421,470.16元),
and V6 `clear_unsupported_investment` deleted them. Cause: the evidence check
removes all whitespace before matching numbers, which glues adjacent table
cells together (`8,000.006,000.00`), so the amount is no longer found as a
separate number. This affects amounts that appear only inside tables.
12 factual attributes per run (4 fields × 3 events) are lost to this bug.

**Missing entity and funding source for 久立 commissioning (005).** The model
left both null on both events.

**Minor formatting differences.** `企业自筹` vs `企业自筹解决`, location with
or without `厂区内` / a city prefix, facility labels.

**Narrative strict accuracy 3.3%.** Exact-string matching of summaries; not a
semantic-quality measure.

## Stability

Event and capacity detection differed across runs only in the two single
false positives above. Factual accuracy varied by 3 attributes.

## Conclusions

1. V6's rule changes generalized: on a new, issuer-disjoint set the event and
   capacity-record scores are the best of any independent evaluation so far.
2. Hard negatives and zero-event documents were handled correctly.
3. One remaining systematic bug: investment amounts inside PDF tables are
   deleted because whitespace removal merges table cells.

## Limitations

- 12 documents, 10 events, 4 capacity records; quote counts with percentages.
- Single annotator; debatable labels (006 IT-platform delay, 005 two events,
  009 zero events) were flagged in the Gold README before evaluation.
- No annual framework plan in this set, so the framework-merge rule is
  untested on unseen data.
- 9 of 12 documents come from stainless, special-alloy or pipe processors.

## Rules after this report

This report and `capacity-v6-holdout-gold-v1` are final. A fix for the
table-number bug is V7 work and needs a new holdout; these 12 documents are
now development data.
