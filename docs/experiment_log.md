# Experiment log

Every evaluation run is archived under `experiments/<run>/` (report, batch
record, predictions and per-document run logs with prompt SHA-256) and listed
in `experiments/registry.csv`. Archive new runs with
`scripts/archive_experiments.py`; archived files are append-only and
`tests/test_frozen_records.py` fails if a frozen Gold file or an archived
report changes.

**Status column.** *Independent* means the system version was committed and
the Gold labels were frozen before the run, and no rule was changed in
response to that run before it was reported. *Development* means the labels
were used, before or after, to change prompts or rules. Only *Independent*
results may be cited as accuracy.

## Pledge extraction (non-steel issuers)

| Run | Documents | Prompt | Event F1 | Status | Note |
| --- | ---: | --- | ---: | --- | --- |
| accuracy_test | 5 | pledge v5 `ac01f3b5` | 100% | Development | Five-document development set |
| blind_test_v1 | 20 | pledge v5 `ac01f3b5` | **73.85%** | **Independent** | Gold `pledge-blind-v1` frozen before the run |
| blind_test_v2 | 20 | pledge v6 `1ee7fa3c` | 92.31% | Development | Prompt changed after viewing blind_test_v1; the current v6 file no longer has this hash, so the run is not reproducible |

All 25 pledge Gold documents come from issuers outside the steel industry.

## Capacity events

| Run | Documents × runs | System | Event F1 | Capacity-record F1 | Factual attributes | Status |
| --- | --- | --- | ---: | ---: | ---: | --- |
| capacity_dev_v2 | 12 × 1 | V2 | 88.0% | 61.5% | 122/176 | Development |
| capacity_dev_v3 | 12 × 1 | V3 | 91.7% | 65.5% | 118/176 | Development |
| capacity_dev_v3_1 | 12 × 1 | V3.1 | 100% | 81.8% | 135/192 | Development |
| capacity_dev_v4 | 12 × 1 | V4 (`0b8b732`) | 100% | 100% | 277/316 | Development |
| **capacity_blind_v4** | 8 × 1 | V4 (`0b8b732`) | **87.5%** | **53.3%** | **122/151** | **Independent** (Gold frozen after the run without viewing predictions) |
| capacity_v5_dev_v4_baseline | 8 × 1 | V4 | 25.3% | 44.4% | 149/193 | Development baseline for V5 |
| capacity_v5_dev_v5_* (prompt_only, 1_prompt, 1_full, 2_normalized, 3_retry, 3_r2, 3_r3, 4_final) | 8 × 1 each | V5 iterations | 95.2–100% | 50–100% | 131–154 | Development |
| **capacity_holdout_v5_r1–r3** | 9 × 3 | V5 (`a50839f`) | **72.7–88.9%** | **22.2–23.5%** | **124–126/159** | **Independent** (Gold `f072403` before first run) |
| **capacity_v6_holdout_r1–r3** | 12 × 3 | V6 (`f08347f`) | **95.2–100%** | **88.9–100%** | **185–188/210** | **Independent** (Gold `5381eee` before first run) |
| capacity_v6_scan_r1 | 12 × 1 | V6 + OCR | 90.0% | 66.7% | 160/192 | Independent measurement of OCR loss |
| capacity_v6_scan_r2 | 12 × 1 | V6 + OCR fix `58bf2ae` | 90.0% | 66.7% | 164/192 | Development (OCR fix made after r1) |
| web_trial, web_trial_v7 | 3 × 1 | V6 / V7 | — | — | — | Qualitative webpage check, no Gold |
| guarantee_dev_v1 | 4 × 1 | Guarantee prompt v1 (`1805779`) | 28.6% | — | 118/132 | Development (Gold v1) |
| guarantee_dev_v2 | 4 × 1 | Guarantee prompt v2 (`ade6873`) | 76.5% | — | 188/230 | Development (Gold v2) |
| guarantee_dev_v3 | 4 × 1 | Guarantee prompt v3 (`5cf6f00`) | 100% | — | 313/328 | Development (Gold v2) — dev freeze; the 15 remaining mismatches are all listed Gold alternatives |
| **guarantee_test_r1–r3** | 6 × 3 | Guarantee v3 (`fbb7d33`) | **95.65%** | — | **216–217/226** | **Independent** (Gold `d76a3c3` before first run) |
| related_dev_v1 | 3 × 1 | Related-party v1 (`2fe3c7d`+fix) | 92.5% (records) | — | 331/337 | Development |
| **related_test_r1–r3** | 4 × 3 | Related-party v1 (`832efb8`) | **98.69% (records)** | — | **1410/1546** | **Independent** (Gold `d05d3d3` before first run; factual rescored with two-pass pairing, first print 1381/1546) |

Known anomaly: `capacity_v5_dev_v5_1_full` reports the same attribute
counts as the V4 baseline although its predictions differ. The report should
be regenerated before any V5.1 number is quoted.

## Replays without new model calls

V6 and V7 rules were also checked by re-normalizing stored raw model outputs
of earlier runs (dev12, blind8, v5_dev8, holdout9). These replays measure
rule changes only and are development evidence: on holdout9 they are fitted
to the errors that motivated the rules.

## Pending independent evaluations

| Module | What is missing |
| --- | --- |
| Capacity V7 (maintenance events, research fields) | New issuer-disjoint Gold including maintenance and overseas projects |
| Guarantee v4 | Released/overdue coverage and a new issuer-disjoint set after the v4 fixes |
| Final test set | Reserved documents from 8 core steel mills, run once after the final freeze |
