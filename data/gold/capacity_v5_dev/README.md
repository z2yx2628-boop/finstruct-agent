# Capacity V5 development gold labels

## Status

- Version: `capacity-v5-dev-gold-v1`
- Labeled date: `2026-09-20`
- Scope: 8 documents and 11 events
- Purpose: V5 prompt, normalization, and evidence-rule development

This is an error-focused development set, not an independent benchmark. Its
scores measure fit to known difficult patterns and must not be reported as
holdout performance.

## Annotation rules

1. An annual fixed-asset investment plan is one framework event. Table rows
   are not split into child events when the disclosed decision approves or
   adjusts the plan as a whole.
2. An announcement that independently delays several named projects produces
   one delay event per project.
3. A project financing or guarantee announcement is not a capacity event when
   project construction is only background context. Financing limits are not
   project investment amounts.
4. An overseas project progress announcement may retain the underlying
   construction event when the progress action and project scale are explicit.
5. Equipment dimensions, temporary output loss, historical planned capacity,
   and product mix are not converted into capacity changes.
6. Output of a newly built production line may be labeled as a product-level
   capacity record even when the announcement states that regulated steel
   capacity does not increase. The record must not be interpreted as net
   industry capacity growth.
7. Month-only completion schedules remain in `timeline_text`; an exact date is
   not fabricated.
8. Investment amounts and funding sources retain the source amount and unit.
9. All Gold confidence values are `1.0` because these files record adjudicated
   labels, not model confidence.

## Material judgments

| File | Judgment |
| --- | --- |
| `capacity_v5_dev_001_600581_bayi_framework.json` | One technical-upgrade framework event for the 48-project annual plan. |
| `capacity_v5_dev_002_600569_angang_framework_adjustment.json` | One framework-adjustment event; cancelled and added table rows are details of the plan-level decision under the current schema. |
| `capacity_v5_dev_004_000709_hbis_plate_construction.json` | The 242万吨/年 value is product-line output, not net new regulated steel capacity. |
| `capacity_v5_dev_005_002843_bichamp_multi_delay.json` | Three independently named delayed projects produce three events. |
| `capacity_v5_dev_006_301217_tongguan_multi_delay.json` | Three independently named delayed projects produce three events; 2024年6月 remains narrative because no exact day is given. |
| `capacity_v5_dev_007_600019_baosteel_overseas_financing.json` | Zero events: the disclosed decision is a financing guarantee. |
| `capacity_v5_dev_008_600282_nangang_overseas_progress.json` | One construction-progress event supported by the signed project agreement. |

The two adjacent-metal delay documents test multi-event structure only. They
do not establish representativeness for steel issuers.

## Evidence-validator limitations

The source facts were checked against all PDF pages. The current deterministic
validator reports four false negatives: three investment values in the
line-broken table of the Taijia announcement and the Chinese-numeral signature
date in the Nangang announcement. These are parser-normalization limitations,
not unsupported Gold fields.
