# Capacity blind-set gold labels

## Freeze status

- Version: `capacity-blind-v1`
- Frozen date: `2026-09-20`
- Manifest: `gold_manifest.lock`
- Scope: 8 documents and 9 events
- Frozen prediction run: `data/manifests/capacity_blind_v4_run.json`

The source PDFs and their rendered pages were reviewed without opening the
frozen prediction JSON files. The gold labels were frozen before the first
accuracy evaluation against those predictions.

## Annotation rules

1. Use only facts explicitly disclosed in each announcement. Unstated fields
   remain `null`.
2. A board-approved investment is labeled `approved`; pending shareholder or
   administrative approval is retained in `timeline_text`.
3. Month-only or year-only schedules remain narrative text rather than being
   converted into fabricated exact dates.
4. Total project investment is recorded in the original amount and unit.
   Registered capital, shareholder contribution and expected revenue are not
   substituted for total investment.
5. Capacity values preserve the original number and unit. Equipment nominal
   size is included only when the announcement explicitly retires or replaces
   that equipment.
6. A framework announcement covering many small projects is one framework
   event unless the announcement makes separate project decisions.
7. Independent delayed projects are separate events.
8. Environmental metrics require a quantified project target or result;
   qualitative environmental descriptions are not labeled as metrics.
9. Evidence snippets are continuous source quotations after whitespace
   normalization.

## Material judgments

| File | Judgment | Rationale |
| --- | --- | --- |
| `capacity_blind_002_601003_liugang_replacement.json` | The retired 1,500 m3 blast furnace is retained as an equipment-size capacity record | The announcement explicitly states that the furnace will be dismantled; the separate 6% figure is an estimated output impact and is not labeled as capacity. |
| `capacity_blind_003_000717_zhongnan_technical_upgrade.json` and `capacity_blind_004_000717_zhongnan_technical_upgrade.json` | Each annual framework plan is one event | The announcement approves one annual investment framework rather than 132 or 156 independently described project decisions. |
| `capacity_blind_005_600282_nangang_delay.json` | Two delay events are labeled | The announcement independently delays the industrial internet project and the integrated smart center project. |
| `capacity_blind_007_000708_citicsteel_construction.json` | One aggregate 1.13 million-ton billet-and-product capacity record is labeled | The announcement states this aggregate annual output; product composition is not duplicated as additional capacity records. |
| `capacity_blind_008_000708_citicsteel_construction.json` | Event type is `technical_upgrade` despite the source filename | The body explicitly describes upgrading existing forging equipment and states that total steelmaking capacity will not increase. |

## Evidence-validator limitations

Schema validation passes for all eight files. The current deterministic
evidence validator reports six false negatives caused by full-width dashes,
Chinese-numeral signature dates, and table-number tokenization. These are
validator limitations rather than unsupported gold facts; the corresponding
facts were visually checked against the PDFs.

After the first evaluation, corrections must create a new version with a
written rationale. Do not overwrite this frozen version based on prediction
errors.
