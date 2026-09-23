# Capacity V5 development set

## Purpose

This eight-document development set targets the main errors observed after the frozen V4 blind evaluation without reusing blind labels as training data. It covers annual investment frameworks, equipment-heavy construction or upgrades, multi-project delays, and overseas project or financing disclosures.

The set is for V5 prompt, normalization, and evidence-rule development. It is not a new blind benchmark and must not be used to claim V5 generalization performance.

## Composition

| Pattern | Documents | Intended stress test |
|---|---:|---|
| Annual framework or adjustment | 2 | Event granularity, summary totals, mixed project actions |
| Equipment-heavy construction or upgrade | 2 | Project versus equipment granularity, product output versus regulated capacity |
| Multi-project delay | 2 | Complete event recall without merging independent projects |
| Overseas progress or financing | 2 | Currency and financing context, project progress, false-positive control |

All eight local PDFs are text-native, have no empty pages, and have unique SHA-256 values. Their official source URLs, checksums, page counts, and parser character counts are recorded in `data/manifests/capacity_v5_sources.csv`.

## Annotation decisions required

1. Framework announcements need a written granularity rule before Gold annotation. Aggregate investment totals must not be copied to every listed project.
2. The two multi-project delay documents should produce three separate delay events each if the announcement gives project-level evidence.
3. The Baosteel financing-guarantee announcement is a hard negative under the current capacity-event schema. Its construction project is background context, not the disclosed event.
4. The Nangang overseas progress announcement may produce one project-progress event, but it is related to a project family already seen in the frozen blind exercise. It can guide V5 development only.

## Scope limitations

- Two delay samples are from steel-adjacent or other metal-sector issuers. They test document structure, not steel-industry representativeness.
- The set is small and deliberately error-focused. Its class proportions do not estimate the production distribution.
- All files are text-native PDFs. OCR, image-only announcements, HTML pages, and table reconstruction remain separate future work.

## Leakage and versioning rule

- Do not modify the frozen V4 predictions, blind Gold, or V1 evaluation report.
- Create V5 Gold labels from these eight source documents under an explicit annotation guide.
- Freeze the V5 extractor before evaluating it on a future untouched issuer-disjoint holdout.
- Report development-set fit and holdout performance separately.

## Reproduction

Raw PDFs remain excluded from Git under the repository policy. The manifest is the reproducible index: download each official URL, verify its SHA-256 value, and parse it with the project PDF parser. When local PDFs are present, `tests/test_capacity_v5_manifest.py` verifies the files against the manifest.
