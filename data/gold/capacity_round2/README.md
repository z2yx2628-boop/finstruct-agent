# Capacity round 2 frozen test

- Selection: six previously unused announcements in `data/manifests/capacity_round2_selection.csv`.
- Extraction system: locked before source download in `data/manifests/capacity_round2_system.lock.json`.
- Status: blocked on source collection. On 2026-09-28, the local shell and browser both returned DNS resolution errors for `static.cninfo.com.cn`; no source PDF has been collected, no Gold has been drafted, and no model extraction has been run.
- Integrity rule: do not substitute search snippets or annual-report summaries for the selected source PDFs. Resume from the frozen selection only after all six original announcements are available, then draft and lock Gold before the single model run.
- Intended composition: four positive capacity-project announcements and two difficult title-matched negatives.
