# Capacity Event Extraction V2 Development Baseline

Recorded at: 2026-09-20 07:42 UTC+02:00

## Scope

- Branch: `codex/capacity-event-v1`
- Dataset: 12 text-based A-share steel company announcement PDFs
- Gold set: 12 documents, 12 primary events, 18 capacity-change
  records, and 2 environmental-metric records
- Prompt: `prompts/capacity_extraction_v2.txt`
- Evaluation report generated at:
  `outputs/capacity_dev_v2/accuracy_report.json`

The generated output directory is intentionally ignored by Git. This file
records the reproducible headline baseline without committing model outputs.

## Automated Verification

- Test suite: 59 passed
- Documents evaluated: 12/12
- Pipeline evidence status: 7 success, 5 needs review, 0 failed

## Accuracy Baseline

| Metric | Result |
| --- | ---: |
| Event precision | 84.62% |
| Event recall | 91.67% |
| Event F1 | 88.00% |
| Document field accuracy | 60/60 (100.00%) |
| Event attribute accuracy | 122/176 (69.32%) |
| Event attribute overfills | 3 |
| Capacity-record precision | 47.06% |
| Capacity-record recall | 88.89% |
| Capacity-record F1 | 61.54% |
| Capacity attribute accuracy | 65/80 (81.25%) |
| Environmental-record precision | 40.00% |
| Environmental-record recall | 100.00% |
| Environmental-record F1 | 57.14% |
| Environmental attribute accuracy | 8/10 (80.00%) |

## Error Concentration

- Development documents 003, 004, 006, and 012 contain the record-level
  detection errors.
- Document 003 contributes ten unexpected capacity records.
- Document 006 contains a primary event-type mismatch.
- Frequent strict field mismatches include `facility_type`,
  `project_purpose`, `technology_description`, and `timeline_text`.

## Interpretation

This is a development-set baseline, not a blind-test result. The same 12
documents were used while tuning the prompt and deterministic normalization,
so the metrics must not be presented as evidence of generalization.

The next iteration should reduce capacity-record false positives before the
eight issuer-isolated blind documents are processed. The blind set must remain
unseen until the code, prompt, schema, gold data, and evaluation policy are
frozen.
