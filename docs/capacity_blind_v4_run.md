# Capacity V4 Isolated Blind Run

The frozen V4 system was run once on the 8-document isolated capacity blind
set on 2026-09-20. No blind Gold JSON files were available during prediction.

## Frozen Inputs

- Code commit: `0b8b73247a3c11030c09cae14a227ce73c1679d4`
- Branch: `codex/capacity-event-v1`
- Prompt: `prompts/capacity_extraction_v4.txt`
- Prompt SHA-256:
  `5989bb4292bbc7ea3dbc49233f62be4858f9b702864f2ff3654724664fe99930`
- Model: `qwen-plus`
- Run manifest: `data/manifests/capacity_blind_v4_run.json`
- Batch report: `outputs/capacity_blind_v4/batch_run.json`
- Predictions: `outputs/capacity_blind_v4/predictions/`

## Run Result

- Documents: 8/8
- Runtime failures: 0
- Evidence status `success`: 3
- Evidence status `needs_review`: 5

`needs_review` is not an accuracy label. It means at least one deterministic
evidence check requires human review. The blind accuracy cannot be reported
until independently produced Gold files exist.

The review signals cover unit support, announcement-date support, and evidence
snippets that include PDF line breaks or ellipses. Predictions must remain
unchanged while Gold is produced.

## Blind-Test Integrity Policy

1. Do not rerun or overwrite the V4 prediction files.
2. Produce Gold by reading each source PDF, not by editing a copy of prediction.
3. Keep annotators blind to prediction JSON where practical.
4. Record uncertain labels and adjudication decisions separately.
5. After all 8 Gold files are frozen, run the existing evaluator once.
6. Do not tune V4 against blind labels. Any future V5 work must use a new
   development set and preserve this V4 report as the independent result.

## Next Step

Create eight same-named Gold JSON files in `data/gold/capacity_blind/`, validate
them against `CapacityDocument`, then evaluate the frozen predictions and write
an independent blind report.
