# Capacity announcement collection v1

## Purpose

This collection is the first corpus for developing and independently checking the steel-industry capacity-event extractor. It contains official, text-native announcement PDFs from CNINFO.

## Layout

- `data/raw/capacity_dev/`: 12 development documents. These may be inspected while refining the schema, prompt, normalizer, and evidence checks.
- `data/raw/capacity_blind/`: 8 blind documents. Do not use these documents or their future gold labels while changing extraction logic.
- `data/manifests/capacity_sources.csv`: source URL, checksum, page count, and extraction metadata for all 20 documents.

The blind issuers do not appear in the development set. All 20 SHA-256 values are unique.

## Validation performed

- PDF opens successfully with PyMuPDF.
- Every file has at least one page.
- Every file yields non-empty text and valid Chinese characters through the current parser dependency.
- Source is an official CNINFO `static.cninfo.com.cn/finalpage` PDF URL.
- SHA-256, page count, and extracted character count are recorded in the manifest.

## Distribution and limitation

| Split | Construction | Technical upgrade | Commissioning | Capacity replacement | Delay | Termination | Suspension |
|---|---:|---:|---:|---:|---:|---:|---:|
| Development | 4 | 3 | 2 | 1 | 1 | 1 | 0 |
| Blind | 3 | 2 | 0 | 2 | 1 | 0 | 0 |

This is suitable for pipeline development and an initial issuer-disjoint blind test, but it is not a final balanced benchmark. Suspension is absent, and commissioning and termination are absent from the blind split. A later benchmark version should add scarce negative-event documents and keep them entirely outside prompt development.

## Leakage rule

Do not create or inspect gold JSON for `capacity_blind` until the extractor version under test has been frozen and its commit hash recorded. After evaluation, keep the original report unchanged and make fixes on a new version.
