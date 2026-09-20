# Capacity V5 Development Set - V4 Baseline

Frozen on 2026-09-20 before any V5 prompt or rule changes. The source corpus
is the eight-document error-focused development set, and the labels are
`capacity-v5-dev-gold-v1`.

This is a development diagnostic, not an independent holdout result. The
original V4 blind evaluation remains the honest generalization baseline.

## Artifacts

- Prompt: `prompts/capacity_extraction_v4.txt`
- Gold: `data/gold/capacity_v5_dev/`
- Predictions: `outputs/capacity_v5_dev_v4_baseline/predictions/`
- Batch report: `outputs/capacity_v5_dev_v4_baseline/batch_run.json`
- Accuracy report: `outputs/capacity_v5_dev_v4_baseline/report.json`
- Run manifest: `data/manifests/capacity_v5_dev_v4_run.json`

## Frozen metrics

| Metric | V4 result |
| --- | ---: |
| Documents evaluated | 8/8 |
| Runtime success / needs review / failed | 6 / 2 / 0 |
| Event TP / FP / FN | 11 / 65 / 0 |
| Event precision / recall / F1 | 14.47% / 100.00% / 25.29% |
| Capacity-record TP / FP / FN | 2 / 5 / 0 |
| Capacity-record precision / recall / F1 | 28.57% / 100.00% / 44.44% |
| Document-field accuracy | 40/40 (100.00%) |
| Factual-attribute accuracy | 149/193 (77.20%) |
| Factual overfills | 7 |
| Narrative strict accuracy | 7/33 (21.21%) |
| Safe canonical all-attribute accuracy | 156/226 (69.03%) |

Environmental-record precision, recall, and F1 display as 100% only because
both Gold and predictions contain zero records. This is a vacuous `0/0`
result and is not evidence of environmental extraction quality.

## Error concentration

1. The Bayi annual framework was expanded into 47 predicted events instead of
   one framework event, producing 46 false positives.
2. The Anyang mid-year framework adjustment was expanded into 19 predicted
   events instead of one framework event, producing 18 false positives.
3. These two framework documents account for 64 of the 65 event false
   positives. Event recall is therefore misleadingly high while precision
   collapses.
4. The Baosteel financing-guarantee hard negative produced one construction
   event and three capacity records from project background text. The model
   did not distinguish the disclosed transaction from contextual project
   facts.
5. Both multi-project delay announcements achieved complete event recall. The
   Taijia prediction nevertheless emitted two historical planned-capacity
   records, while investment and funding fields were often omitted.
6. The Tongguan prediction converted month-only `2024年6月` into fabricated
   exact dates (`2024-06-30`) and overfilled project entities.
7. The Hbis construction event and its product output were detected, but the
   project name, total investment, currency, and funding source were missed.

## V5 development targets

1. Add an announcement-level granularity gate: annual fixed-asset frameworks
   and framework adjustments produce one aggregate event unless the task
   explicitly requests project-row extraction.
2. Add a main-disclosed-event gate: financing and guarantee announcements are
   hard negatives when construction appears only as background context.
3. Preserve multi-project delay splitting while suppressing historical planned
   capacity records.
4. Prohibit conversion of month-only schedules into exact calendar dates.
5. Improve table-header association for project total investment and funding
   source without relaxing evidence requirements.

## Next gate

Create `prompts/capacity_extraction_v5.txt` and deterministic regression rules
for the five targets above. Re-run this development set until the framework
and hard-negative false positives are removed without losing the 11 Gold
events. Then freeze V5 before collecting and labeling a new issuer-disjoint
holdout.
