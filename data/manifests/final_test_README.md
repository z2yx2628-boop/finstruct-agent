# Final test set (reserved)

Selected 2026-09-24 from titles found by web search only; **no document is opened,
parsed, run or annotated until the final system freeze (planned 2026-10-13).**
Only file hashes are recorded (`final_test_sources.csv`, written by the download script).

Issuers: 7 of the 8 core mills reserved in `docs/steel_universe.md` (鞍钢, 马钢, 包钢,
方大特钢, 新钢, 沙钢, 太钢不锈), one document each.

Change 2026-09-24 (before any document was opened): final_003 山东钢铁 was dropped
because its only source (the issuer group website) could not be downloaded from the
project network. The remaining ids keep their numbers; final_003 is intentionally absent.

| Task | Documents |
| --- | --- |
| related_party | final_001–002, 004–008 (7 docs: estimate tables, an adjustment, an execution report, a framework-agreement supplement) |
| capacity (V7 maintenance, webpage format) | final_web_001 |

Known gap: no guarantee or new-capacity announcement from these 8 mills could be found
through reachable mirrors, and 方大特钢's guarantee announcements are excluded because one
was used for guarantee development. Guarantee is evaluated by its own frozen test set.

Procedure after the freeze: annotate Gold from the sources → write gold_manifest.lock →
run each task 3 times → report once, whatever the result.

## Change 2026-09-27: Gold annotation moved forward (written before any final-test document is opened)

**What changes.** Gold annotation starts now instead of after 2026-10-13. Nothing else in the
procedure changes: no final-test document has been opened, parsed, run or annotated before this
note was committed.

**Why this is safe.** The final test measures direction ① (structured extraction) only:
related_party for final_001–002 and 004–008, capacity for final_web_001. The system under test is
therefore the frozen extraction system, tag `extraction-freeze-2026-09-24` (commit `8a0abba`).
It is declared here as the **final** version for this test set.

Checked on 2026-09-27 (`git diff --ignore-cr-at-eol extraction-freeze-2026-09-24 HEAD -- src prompts schemas`):
- `prompts/` and `schemas/`: no changes.
- `src/`: changed files are direction ②/③ only (`analyze`, `chain_inputs`, `fragility`,
  `network_view`, `propagation`, `sources`, `validity`), plus one **additive** function in
  `entity_resolver.py` (`groups_as_of`). The extraction path `related_party_normalizer →
  group_relationship → entity_resolver.resolve` is unchanged, and `data/reference/entities.csv`
  and `group_prefixes.csv` are unchanged since the tag. Extraction output is therefore identical
  to the tagged system's.

**Commitments from now on.**
1. The extraction modules (`src/pipeline.py`, the parsers, extractors, normalizers and
   evidence validators), `prompts/`, `schemas/`, `data/reference/entities.csv` and
   `group_prefixes.csv` are not modified. Directions ②/③ and the web UI may still change,
   because they are not measured by this test.
2. Order: annotate Gold per `docs/annotation_guidelines.md` → write `data/gold/final_test/gold_manifest.lock`
   (SHA-256 of each Gold file, `system_under_test_commit: 8a0abba`) and commit it → only then
   run the system on the final test set.
3. Each task is run 3 times. All three results are reported (mean and range), whatever they are.
   No prompt, rule or Gold change is made after the first run; a Gold error found after a run is
   reported as a correction note with both scores, never silently fixed.
4. If an extraction-module change ever becomes necessary after this note, the final-test result
   can no longer be called blind (the developers have seen the documents while annotating); the
   report must say so and name the later commit as the system tested.
