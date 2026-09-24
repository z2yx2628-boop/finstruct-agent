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
