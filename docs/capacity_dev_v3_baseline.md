# Capacity Event Extraction V3 Development Baseline

Recorded at: 2026-09-20 21:03 UTC+02:00

## Scope

- Branch: `codex/capacity-event-v1`
- Dataset: 12 text-based A-share steel company announcement PDFs
- Gold set: 12 documents, 12 primary events, 18 capacity-change
  records, and 2 environmental-metric records
- Prompt: `prompts/capacity_extraction_v3.txt`
- Evaluation report generated at:
  `outputs/capacity_dev_v3_2_accuracy_report.json`

The generated output directory is intentionally ignored by Git. This file
records the reproducible headline baseline without committing model outputs.

## Automated Verification

- Test suite: 70 passed
- Documents evaluated: 12/12
- V3 model run: 7 success, 5 needs review, 0 failed
- Final deterministic replay: 12/12 prediction files evaluated

## V2 To V3 Comparison

| Metric | V2 | V3 |
| --- | ---: | ---: |
| Event precision | 84.62% | 100.00% |
| Event recall | 91.67% | 100.00% |
| Event F1 | 88.00% | 100.00% |
| Document field accuracy | 100.00% | 100.00% |
| Event attribute accuracy | 69.32% | 70.31% |
| Event attribute overfills | 3 | 3 |
| Capacity-record precision | 47.06% | 100.00% |
| Capacity-record recall | 88.89% | 100.00% |
| Capacity-record F1 | 61.54% | 100.00% |
| Capacity attribute accuracy | 81.25% | 75.56% |
| Capacity attribute overfills | not recorded | 2 |
| Environmental-record precision | 40.00% | 100.00% |
| Environmental-record recall | 100.00% | 100.00% |
| Environmental-record F1 | 57.14% | 100.00% |
| Environmental attribute accuracy | 80.00% | 80.00% |

## V3 Error Controls

- Merge a secondary capacity-replacement event into the primary event when
  both refer to the same named project.
- Exclude equipment dimensions from non-replacement capacity records.
- Exclude equipment-count breakdowns when a formal aggregate project
  capacity is already disclosed.
- Exclude current-asset background descriptions without an explicit
  retirement action.
- Exclude historical planned output from termination, suspension, and delay
  events.
- Exclude regulatory or industry-standard thresholds from project-specific
  environmental metrics.
- Preserve project investment values split across PDF line boundaries.
- Reclassify existing-asset technology migration and multi-system rebuilds
  as technical upgrades.

## Remaining Error Concentration

- Record detection is complete on this development set, but strict pass is
  still false because attribute values do not exactly match all Gold values.
- Frequent mismatches remain in `project_purpose`, `timeline_text`,
  `technology_description`, `project_location`, and nested record labels.
- Many mismatches are summarization-granularity differences, but some are
  substantive omissions and must be separated before further tuning.
- Capacity attribute accuracy decreased even while record detection improved;
  record-level F1 must therefore not be used as a substitute for field-level
  accuracy.

## Interpretation

This is a tuned development-set result, not a blind-test result. The same 12
documents were used to derive and verify V3 rules, so the 100% record-level
scores do not establish generalization.

The next stage is attribute-error attribution and canonicalization on the
development set. After the schema, prompt, normalizer, Gold policy, and code
are frozen, the eight issuer-isolated blind documents should be run exactly
once and reported without further blind-driven tuning.
