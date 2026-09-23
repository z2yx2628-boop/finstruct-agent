# Capacity holdout Gold labels

## Status

- Version: `capacity-holdout-gold-v1` — **FROZEN 2026-09-23**
- Drafted: 2026-09-23, from source PDFs only
- Scope: 9 documents, 9 events, 5 capacity records
- Annotator: one annotator; no second-annotator adjudication before freeze
- Frozen system under test: V5, commit `a50839f`

No V5 prediction was run on any holdout document before this freeze.
`gold_manifest.lock` records the SHA-256 of every Gold file.

## Annotation rules

The V5 development rules (`data/gold/capacity_v5_dev/README.md`) apply
unchanged. In particular:

1. An annual investment framework is one event; its listed items are not
   split into child events or capacity records.
2. An announcement that approves several independently named projects, each
   with its own name and investment amount, produces one event per project.
3. A delay announcement produces one event per delayed project. Projects
   mentioned only as already completed or as background are not events.
4. Planned capacity in the name of a delayed or terminated project is not a
   capacity record.
5. Equipment specifications are not capacity records; explicit annual output
   increases are.
6. A capacity breakdown beside an explicit total is not split into extra
   records; existing total capacity after the change is not a new record.
7. Month-only schedules stay in `timeline_text`.
8. `announcement_date` is the date printed at the end of the announcement.
9. All confidence values are `1.0` (adjudicated labels).

## Material judgments (frozen as drafted)

| File | Draft label | Alternative a reviewer may choose |
| --- | --- | --- |
| 001 本钢板材 | One framework event, no capacity record, although item 1 explicitly raises 1# caster capacity from 195 to 230万吨/年. | Add one capacity record for the caster (conflicts with the V5 dev rule used for Bayi). |
| 001 本钢板材 | `announcement_date` 2024-04-29 (printed date); CNINFO lists 2024-04-28. | — |
| 002 酒钢宏兴 | `technical_upgrade`: project is named 工艺装备提升及产品结构调整 at an existing plant. | `capacity_construction`, because it builds new casting, 4200mm plate and double high-speed bar lines. |
| 003 抚顺特钢 | Two events, one per named project (55,634 and 45,000 万元; total 10.06亿元). | One aggregate event of 10.06亿元. |
| 003 抚顺特钢 | Three capacity records (6940, 5400, 9720 吨/年). Furnace counts and 12吨 furnace size are equipment specs. | — |
| 004 新兴铸管 | `technical_upgrade`; 194万吨/年 dry coke capacity recorded. `project_entity` null because the JV is unnamed. | `capacity_replacement`, because the text says the ovens are built 通过产能置换. |
| 005 甬金股份 | One delay event. The 35万吨 project is already in production and is not an event. Only phase 1 has an exact new date, so `delay_until_date` = 2025-03-31. | — |
| 006 武进不锈 | One delay event; `project_entity` null because no implementing subsidiary is named. | — |
| 007 甬金股份 | One termination event with no investment amount (none disclosed in this announcement). | — |
| 008 三钢闽光 | **Zero events.** The suspended item is a framework agreement on capacity-quota cooperation that never became a project. | One `suspension` event. If chosen, the holdout gains its only suspension example. |
| 009 首钢股份 | One commissioning event with one 95万吨/年 record; the 60+35 breakdown and the 150万吨/年 total are not extra records. The value is stated as capacity after reaching design output. | — |

## Selection notes

- 005 and 006 were selected as multi-project delays from their titles, but
  each delays only one project. They test delay extraction with a
  non-delayed sibling project in the same table, not multi-event splitting.
- 005, 006, 007, 010 and 011 come from stainless or steel-pipe processors,
  which are steel-adjacent rather than integrated steelmakers.
- 012 (杭钢 data centre) is intended as a hard negative.

## Dropped documents

Three further selected documents (久立特材 commissioning, 金洲管道 60万吨
construction, 杭钢 data-centre hard negative, and their replacements) could
not be downloaded because CNINFO repeatedly reset or timed out the
connection. The holdout was frozen at 9 documents instead of 12. As a result
it contains no hard-negative non-capacity project and only one construction-
type document outside the framework/upgrade patterns.

## Limitations of this freeze

1. Single annotator. The judgments in the table above were frozen as drafted
   without independent review. A reviewer who disagrees must create
   `capacity-holdout-gold-v2`; this v1 and any report made from it stay
   unchanged.
2. Nine documents and 9 events is a small sample. Report counts alongside
   percentages.
3. 005/006 are single-project delays; 008 is a zero-event document.

## Evaluation rule

Run frozen V5 (commit `a50839f` or a later commit that changes only data and
docs) three times on `data/raw/capacity_holdout/` and report every run. Do
not change the prompt or rules in response to holdout results.
