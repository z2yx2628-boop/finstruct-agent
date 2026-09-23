# Capacity V6 holdout Gold labels

## Status

- Version: `capacity-v6-holdout-gold-v1` — FROZEN 2026-09-23
- Scope: 12 documents, 10 events, 4 capacity records, 3 zero-event documents
- System under test: V6, commit `f08347f` (committed before this Gold was
  drafted; no V6 prediction has been run on these documents)
- Annotator: one annotator, drafted from source PDFs only; no second review
- Issuers are disjoint from every earlier capacity split (dev, blind, v5_dev,
  holdout v1)

## Annotation rules

The V5 development rules (`data/gold/capacity_v5_dev/README.md`) and the
holdout v1 rules (`data/gold/capacity_holdout/README.md`) apply unchanged.

## Material judgments (frozen as drafted)

| File | Label | Alternative |
| --- | --- | --- |
| 001 永兴 | Commissioning event; 25万吨/年 capacity from the project name; `commissioning_date` null (text says 近日). | — |
| 002 永兴 | Technical upgrade, no capacity record (no stated output). | — |
| 003 常宝 | Construction; 30万吨/年 recorded from “项目建成后年生产…30万吨”. Entity is the implementing grandchild company. | Entity = listed company. |
| 004 久立 | Construction; 20000吨/年 from the project name. | — |
| 005 久立 | **Two commissioning events**, one per named fundraising project; only the aerospace project has a capacity (1000吨/年). Status `commissioned` although the text says trial operation precedes formal operation. | One event; or status `under_construction`. |
| 006 鸿路 | Delay event for an IT platform project, consistent with how v5_dev labelled an R&D-centre delay. | Zero events (not a capacity project). |
| 007 广大 | Delay; `delay_until_date` null (2024年12月 is month-only). Existing 2000吨 capacity is background. | — |
| 008 盛德 | Delay; investment kept in 元 as printed. | — |
| 009 河钢资源 | **Zero events.** A flood-driven temporary halt of copper-mine production is an operational disruption, not a capacity-project decision. | One `suspension` event. |
| 010 金洲 | **Suspension event** (暂缓实施) for the re-registered 100万吨 project; its planned capacity is not a record; no investment amount is disclosed. | Project name = original 60万吨 project. |
| 011 重庆钢铁 | Zero events: bid for existing production-line assets. | — |
| 012 杭钢 | Zero events: data-centre project, not steel capacity. | One construction event. |

## Composition and limitations

- Commissioning 2 docs (3 events), construction 2, technical upgrade 1,
  delay 3, suspension 1, zero-event 3 (including two hard negatives).
- No annual framework plan could be sourced for these issuers, so V6's
  framework-merge rule is not tested here.
- 9 of 12 documents come from stainless, special-alloy or pipe processors;
  009 is a mining issuer.
- Small sample: report counts beside percentages.

## Evaluation rule

Run frozen V6 (`f08347f`, or a later commit that changes only data, docs or
scripts) three times and report every run. Do not change prompt or rules in
response to these results. A reviewer who disagrees with a label creates
`capacity-v6-holdout-gold-v2`; this version stays unchanged.
