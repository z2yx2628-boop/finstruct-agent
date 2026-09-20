# Capacity Event Extraction V4 Development Baseline

Frozen on 2026-09-20 after evaluation on the 12-document capacity
development set. The 8-document isolated blind set was not opened or run
during V4 development.

## Artifacts

- Prompt: `prompts/capacity_extraction_v4.txt`
- Predictions: `outputs/capacity_dev_v4/predictions/`
- Accuracy report: `outputs/capacity_dev_v4/accuracy_report.json`
- Attribute analysis: `outputs/capacity_dev_v4/attribute_analysis.json`
- Development gold: `data/gold/capacity_dev/`

## Frozen Metrics

| Metric | V3 | V4 |
| --- | ---: | ---: |
| Documents evaluated | 12/12 | 12/12 |
| Event detection F1 | 100.00% | 100.00% |
| Capacity record detection F1 | 100.00% | 100.00% |
| Environmental record detection F1 | 100.00% | 100.00% |
| Document field accuracy | 100.00% | 100.00% |
| Factual attribute accuracy | 83.86% | 87.66% |
| Capacity attribute accuracy | 75.56% | 85.56% |
| Environmental attribute accuracy | 80.00% | 100.00% |
| Narrative strict accuracy | 16.67% | 8.33% |
| Safe canonical all-attribute accuracy | 77.56% | 79.83% |
| Attribute overfills | 5 | 2 |

V4 is accepted as the next development baseline because all three record
detection F1 scores remain at 100%, factual attributes improve, and overfills
fall. The strict narrative score is disclosed separately and is not treated as
solved: exact-string comparison penalizes valid paraphrases, but some rows also
contain genuine omissions. No fuzzy matcher is used to inflate the strict score.

## V4 Changes

- Separates factual attributes from narrative summary fields in evaluation.
- Adds conservative canonical formatting metrics without changing strict pass.
- Produces an auditable mismatch classification report.
- Rejects Chinese-unit equipment dimensions as capacity records.
- Recovers a missing single-project formal capacity only from explicit
  `生产规模`, `新增产能`, or `设计产能` evidence.
- Preserves per-device values such as `3×35t` instead of multiplying them.
- Canonicalizes two explicitly defined environmental metric names.
- Rejects announcement, pre-production acceptance, and partial-facility dates
  as whole-project commissioning dates.

## Remaining Development Risk

- Narrative fields need semantic human review; strict string accuracy alone is
  not a valid semantic-quality measure.
- Remaining factual differences are concentrated in project location, funding
  source, project entity, investment fields, and facility labels.
- The formal-capacity recovery rule is intentionally limited to one-event
  documents. Multi-project documents still require explicit event association.
- These results are development-set results and do not estimate generalization.

## Next Gate

Run the 8-document isolated capacity blind set once with the frozen V4 code and
prompt. Do not tune V4 on blind labels. Report the same metrics, plus success,
needs-review, and failure counts. If the blind result misses the agreed gate,
start V5 using a new development set rather than changing V4 against the blind
answers.
