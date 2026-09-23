# Capacity Event Extraction V5 Development Freeze

Frozen on 2026-09-23 after four evaluation runs on the eight-document V5
development set (`capacity-v5-dev-gold-v1`). This is a development-set fit,
not a generalization estimate. The frozen V4 blind evaluation
(`docs/capacity_blind_v1_evaluation.md`) remains the only independent result
until V5 is evaluated on a new issuer-disjoint holdout.

## Frozen system

- Code commit: `efddd250f58de9858c7ae211111b7c3c88488657`
- Branch: `codex/capacity-event-v1`
- Model: `qwen-plus`, `temperature=0`
- Prompt: `prompts/capacity_extraction_v5.txt`

SHA-256 of the frozen working-tree files (Windows checkout, CRLF line
endings):

| File | SHA-256 |
| --- | --- |
| `prompts/capacity_extraction_v5.txt` | `870d3781eed6ea723dddd0b3c8ba67f38f10fe56b22f1b48c2f33d4e7d736985` |
| `src/llm_extractor.py` | `4a7ad8c070ac32b92b87dd336776316a89468032ec0aaf15f62983d0fb4d2348` |
| `src/capacity_normalizer.py` | `fdd95fb744acb4b2f73aede6c49b430103ad97972be55452502be7bd4ed6b583` |
| `src/capacity_empty_retry.py` | `d0bc7083dd2f30471eb086561498a48dbe85c1ba0b3d6fa031f284117cdc5661` |
| `src/event_normalizer.py` | `8505a2b16ff47e7418994b27f1d6e52568c6fc864da2c2adbf1cc95526d1ead1` |
| `src/capacity_evidence_validator.py` | `ba9f00a61446028187e00ec487176c17c9ab5a9238a4d7dadb6e10a92271c8a7` |
| `src/capacity_accuracy_evaluator.py` | `99202283e298df2e28983f7bb0b5d9e604661573998ac919ed51f5f735c18928` |
| `data/gold/capacity_v5_dev/gold_manifest.lock` | `c0f0b5695a9526b64cbd31f021072879329f650d7fb79c088302bf7df7458b06` |

Unit tests: 102 passed at commit `07da976`; commit `efddd25` adds one
normalizer test (103 expected).

## Official V5 result

Run: `outputs/capacity_v5_dev_v5_4_final/` (commit `efddd25`).

| Metric | V4 baseline | V5 final |
| --- | ---: | ---: |
| Documents evaluated | 8/8 | 8/8 |
| Runtime success / needs review / failed | 6 / 2 / 0 | 6 / 2 / 0 |
| Event TP / FP / FN | 11 / 65 / 0 | 11 / 0 / 0 |
| Event precision / recall / F1 | 14.47% / 100.00% / 25.29% | 100.00% / 100.00% / 100.00% |
| Capacity-record TP / FP / FN | 2 / 5 / 0 | 2 / 0 / 0 |
| Capacity-record F1 | 44.44% | 100.00% |
| Document-field accuracy | 40/40 (100.00%) | 40/40 (100.00%) |
| Factual-attribute accuracy | 149/193 (77.20%) | 151/193 (78.24%) |
| Factual overfills | 7 | 4 |
| Narrative strict accuracy | 7/33 (21.21%) | 7/33 (21.21%) |
| Safe canonical all-attribute accuracy | 156/226 (69.03%) | 158/226 (69.91%) |

Environmental-record metrics remain a vacuous `0/0` because neither Gold nor
predictions contain environmental records in this set.

## Run-to-run stability

The model output is not fully deterministic at `temperature=0`: the V5.2 run
(2026-09-21) returned no event for the Nangang overseas-progress document,
while all later runs of the same prompt recovered it on the first call.
Stability was therefore measured before freezing.

| Run | Commit | Event TP/FP/FN | Capacity TP/FP/FN | Factual accuracy | Overfills |
| --- | --- | ---: | ---: | ---: | ---: |
| `v5_3_retry` | `07da976` | 11/0/0 | 2/0/0 | 154/193 (79.79%) | 4 |
| `v5_3_r2` | `07da976` | 11/0/0 | 2/1/0 | 153/193 (79.27%) | 2 |
| `v5_3_r3` | `07da976` | 11/0/0 | 2/0/0 | 151/193 (78.24%) | 3 |
| `v5_4_final` | `efddd25` | 11/0/0 | 2/0/0 | 151/193 (78.24%) | 4 |

- Event detection was identical in all four runs, document by document.
- Factual-attribute accuracy ranged from 78.24% to 79.79%. Report it as a
  range, not as a single point value.
- The empty-event retry did not trigger in any of the four runs. It is a
  safety net for the V5.2 failure mode, verified by unit tests and by checking
  that its trigger matches the Nangang agreement title, but its live
  effectiveness has not been observed.
- The `v5_3_r2` capacity false positive was an investment amount
  (`76,781 万元`) emitted as blast-furnace capacity. Commit `efddd25` removes
  capacity records whose unit is monetary; no capacity false positive
  occurred in the final run.

## V5 changes relative to V4

1. Announcement-level granularity: annual frameworks and framework
   adjustments produce one aggregate event (removed 64 of 65 V4 event FPs).
2. Main-disclosed-event gate: financing and guarantee announcements with
   construction only as background are hard negatives.
3. Multi-project delay splitting is preserved; historical planned capacity is
   removed from delay events.
4. Month-only schedules are no longer converted into exact calendar dates;
   exact dates with PDF spacing are still accepted.
5. Binding project agreements are distinguished from financing agreements and
   overseas project-progress events are preserved.
6. A second model call is made only when the first returns no events and the
   text contains a signed project agreement whose title states a tonnage
   capacity.
7. Capacity records with monetary units are removed.

## Remaining errors in the final run

Field mismatches are concentrated in event-level descriptive and investment
fields, not in event or capacity detection:

| Field | Mismatches |
| --- | ---: |
| `timeline_text` | 11 |
| `project_purpose` | 11 |
| `project_entity` | 8 |
| `investment_amount` / `investment_unit` / `investment_currency` | 6 each |
| `funding_source` | 6 |
| `source_page` | 6 |
| `technology_description` | 4 |
| `project_name` | 3 |
| `facility_type` (capacity record) | 1 |

- Hbis plate construction still misses project name, total investment
  (79.67 亿元), currency and funding source. Table-header association for
  investment fields remains unsolved.
- The two multi-project delay documents account for most `source_page`,
  investment and funding mismatches.
- Overfills: three subsidiary project entities in the Tongguan delay
  document, plus a generic purpose and facility type in the Nangang document.
- Narrative fields are scored by exact string match and are not a valid
  semantic-quality measure.

## Open item

The stored `capacity_v5_dev_v5_1_full/report.json` shows attribute metrics
identical to the V4 baseline although its predictions differ. That report
should be regenerated before V5.1 numbers are quoted anywhere. It does not
affect the V5 final result above.

## Next gate

1. Do not change the prompt or rules after this freeze.
2. Collect a new issuer-disjoint capacity holdout (target 8-10 documents)
   covering the same four stress patterns plus ordinary construction,
   commissioning and termination announcements.
3. Produce and freeze holdout Gold from source PDFs before any V5 prediction
   on those documents.
4. Run frozen V5 once (preferably three times to report a range) and report
   holdout metrics separately from this development fit.
