# Capacity V5 holdout evaluation

## Frozen inputs

- System under test: V5, commit `a50839f` (prompt SHA-256 `870d3781eed6ea723dddd0b3c8ba67f38f10fe56b22f1b48c2f33d4e7d736985`)
- Model: `qwen-plus`, `temperature=0`
- Gold: `capacity-holdout-gold-v1`, commit `f072403` (committed 15:29:05 local);
  first prediction run started 15:29:14 local
- Corpus: 9 documents, 9 Gold events, 5 Gold capacity records; issuers
  disjoint from every earlier capacity set
- Runs: 3 (`outputs/capacity_holdout_v5_r1..r3`)

No prompt, rule or Gold change was made after the first holdout prediction.

## Official results (frozen evaluator, all three runs)

| Metric | r1 | r2 | r3 |
| --- | ---: | ---: | ---: |
| Event TP / FP / FN | 8 / 5 / 1 | 8 / 1 / 1 | 8 / 5 / 1 |
| Event F1 | 72.73% | 88.89% | 72.73% |
| Capacity-record TP / FP / FN | 2 / 11 / 3 | 2 / 10 / 3 | 2 / 10 / 3 |
| Capacity-record F1 | 22.22% | 23.53% | 23.53% |
| Document-field accuracy | 44/45 (97.78%) | 44/45 (97.78%) | 44/45 (97.78%) |
| Factual-attribute accuracy | 126/159 (79.25%) | 124/159 (77.99%) | 126/159 (79.25%) |
| Narrative strict accuracy | 4/24 (16.67%) | 4/24 (16.67%) | 4/24 (16.67%) |
| Safe canonical all-attribute accuracy | 131/183 (71.58%) | 130/183 (71.04%) | 131/183 (71.58%) |

Headline: event F1 72.7–88.9%, capacity-record F1 22–24%, factual-attribute
accuracy 78.0–79.3% over three runs.

## Comparison

| Metric | V4 blind (8 docs, 1 run) | V5 dev fit (8 docs, 4 runs) | V5 holdout (9 docs, 3 runs) |
| --- | ---: | ---: | ---: |
| Event F1 | 87.50% | 100% | 72.7–88.9% |
| Capacity-record F1 | 53.33% | 100% | 22.2–23.5% |
| Document-field accuracy | 95.00% | 100% | 97.78% |
| Factual-attribute accuracy | 80.79% | 78.2–79.8% | 78.0–79.3% |

The V5 development fit did not generalize. Event F1 on the holdout is in the
same range as the V4 blind result and capacity-record F1 is lower. The 100%
development scores must not be quoted as an estimate of accuracy on new
announcements.

## Error analysis (r1 unless stated)

### Events

| Doc | Result | Cause |
| --- | --- | --- |
| 001 本钢 framework | r1, r3: 1 TP + 4 FP; r2: 1 TP | The framework-granularity behaviour held in one run of three; in r1 and r3 four listed items were emitted as separate events. |
| 002 酒钢 | 1 FP + 1 FN every run | Predicted `capacity_construction`; Gold is `technical_upgrade`. This Gold label was flagged as debatable before evaluation (the project builds new casting, plate and bar lines). |
| 003–009 | correct every run | Includes the zero-event 三钢 cooperation suspension and the 甬金 termination. |

### Capacity records

1. **Evaluator pairing artifact (3 FP + 3 FN, all runs).** 抚顺 003 has two
   events of the same type. The model's three capacity records (6940, 5400,
   9720 吨/年) are correct, but the evaluator paired Gold event 1 with the
   predicted energy-saving event, because predicted project names contain
   PDF spaces and tie on every strict attribute. Re-pairing by
   whitespace-insensitive project name (diagnostic only, not applied to the
   official numbers) gives r1 capacity TP / FP / FN = 5 / 8 / 0.
2. **Planned capacity of a delayed or terminated project.** 甬金 22万吨
   (005, r1 only), 武进 6000吨 (006, all runs), 甬金印尼 70万吨 (007, all
   runs).
3. **Breakdown beside a total (2 FP, all runs).** 首钢 009: the 60 and 35
   万吨/年 components were emitted beside the 95万吨/年 total.
4. **Framework items (3 FP, all runs).** 本钢 001: caster and coating-line
   capacities were emitted, even in r2 where event granularity was correct.

### Attributes

**Investment deletion by the normalizer (largest single cause).** In every
run the model extracted the correct investment for 6 events (本钢 194500万元
= 19.45亿元, 酒钢 500000万元, 抚顺 55634 and 45000万元, 新兴 25亿元, 甬金
122868万元). All six equal the Gold amount. The V5
`clear_unsupported_investment` rule then deleted amount, unit, currency and
funding source, because it only accepts amounts beside one of five phrases
(项目总投资, 项目投资总额, 项目总投资额, 预计总投资, 计划总投资). The holdout
uses 计划安排投资, 项目核定投资额, 投资金额, 项目概算投资, and a table header
split across lines. The rule was added to stop development-set overfills and
is fitted to that wording.

**Commissioning-date deletion.** 首钢 009 `commissioning_date` 2020-04-29 was
correct and was deleted by `clear_unsupported_commissioning_date`: the source
reads `于 2020 年 4 月 29 日投产` (PDF spaces, plain 投产), which the rule's
segment and marker checks do not accept.

**Document fields.** One error: announcement number `临 2023-017` kept its
PDF space.

## Stability

Event detection differed across runs only on 本钢 001. All other
per-document event and capacity outcomes were identical in all three runs.
Factual accuracy varied by 2 attributes. The empty-event retry did not
trigger.

## Conclusions

1. V5 reliably identifies document fields, single-project event types,
   zero-event non-project announcements, delays and terminations.
2. The main weaknesses on unseen issuers are deterministic post-processing
   rules fitted to development wording: investment deletion,
   commissioning-date deletion, and incomplete removal of planned or
   breakdown capacity.
3. Framework granularity is not stable run to run.
4. Part of the capacity-record error is an evaluator pairing artifact.

## Limitations

- 9 documents, 9 events, 5 capacity records; quote counts beside
  percentages.
- Single annotator; the 002 event type and the 008 zero-event label were
  flagged as debatable before evaluation.
- No hard-negative non-capacity project (three selected documents could not
  be downloaded).
- Five of nine documents come from stainless or pipe processors.

## Rules after this report

This report and `capacity-holdout-gold-v1` are final and must not be edited.
Any V6 work (relaxing investment and date evidence rules, fixing evaluator
pairing, suppressing planned and breakdown capacity) needs a new holdout;
these nine documents are now development data.
