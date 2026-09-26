# Final-test Gold (final-test-gold-v1) — draft, not frozen

## Status
- System under test: `extraction-freeze-2026-09-24` (commit `8a0abba`); see `data/manifests/final_test_README.md`.
- Annotator: （填写姓名） · Annotation dates: （填写） · Second review: none / （填写）.
- The Gold is written from the source files only. The annotator never opens a model prediction for
  these documents (there are none yet: the system has not been run on them).
- Frozen by `gold_manifest.lock` (`python scripts/final_gold.py lock`) before the first run.

## Final-test scope rules (written 2026-09-27, before any final-test document was opened)
The Gold encodes what the frozen schema and prompt define as the correct output. Four of the
documents are not plain annual estimates, so how they map to the schema is fixed here in advance,
from `prompts/related_party_extraction_v1.txt` alone:

| Document type | Records | Field rules |
| --- | --- | --- |
| Annual estimate (001, 004, 005) | One record per row of the main-body current-year estimate table (prompt rules 5–9) | As in `related_test` |
| Execution + next-year estimate (002) | Rows of the **next-year estimate** table only; the execution (actual) table generates no records (rule 7) | `prior_year_actual_amount` = actual column of the same row of the estimate table if printed there, else null |
| Adjustment of the current-year estimate (006) | One record per row of the adjustment table that states an **adjusted estimate** | `estimated_amount` = amount **after** adjustment (调整后预计金额); `prior_year_actual_amount` = null unless the same row prints the **previous year's** actual (a current-year year-to-date column is not prior-year); `estimate_year` = the year being adjusted; `total_*` = adjusted total if printed |
| Execution report only (007) | If the document contains no estimate for a coming period: **0 records** (hard negative, rule 7); document fields still annotated. If it also contains a next-year estimate table, annotate that table as for 002 | — |
| Framework-agreement supplement (008) | If the document prints annual transaction amounts or caps by category (and party) for a stated year, each row is one record with `estimated_amount` = the cap for the **first** year listed and `estimate_year` = that year; a narrative agreement with no amounts → 0 records | Other years' caps are recorded only in Material judgments |
| Webpage, capacity (final_web_001) | Per guidelines §3 (V7): a temporary shutdown or maintenance is one `maintenance` event; nothing goes into `capacity_changes`; shutdown / output-loss fields only when stated | `source_page` = the parser's text block (see `source_text/final_web_001.txt`); `announcement_date` = page publish date |

Where a document does not fit any row above, choose the reading closest to the prompt rules, and record the
choice and the alternative in the table below. Results are reported per document type as well as overall,
so the non-estimate types (006–008) are visible separately.

## Material judgments
| File | Label | Alternative |
| --- | --- | --- |
| | | |

## Per-document summary (fill in after annotating)
| File | Issuer | Pattern | Records |
| --- | --- | --- | --- |
