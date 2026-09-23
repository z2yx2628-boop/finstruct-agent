# Capacity development gold labels

## Annotation rules

1. `announcement_date` is the date printed in the announcement signature, not the next-day CNINFO publication directory date.
2. A field is `null` when the announcement does not disclose it precisely. General knowledge and external sources are not used to fill missing values.
3. `investment_amount` records total project investment only. Shareholder contribution, registered capital, unused proceeds, and expected revenue are not substituted for project investment.
4. Capacity values preserve the number and unit stated in the announcement. Annual output, equipment count, and equipment nominal size are not converted into one another.
5. `approved` means the disclosed investment plan has received the corporate approval described by the announcement. Remaining administrative permits are preserved in `timeline_text`.
6. `commissioned` means the announcement states that the relevant project or material production unit has begun operation. If the exact commissioning day is not stated for the whole project, `commissioning_date` remains `null`.
7. A proposed termination still receives `event_type: termination`, but `project_status` remains `null` when shareholder or bondholder approval is outstanding.
8. The phrase `2021年9月末` is normalized to `2021-09-30`; the original phrase is retained in evidence.
9. Regulatory emission limits are not labeled as project environmental performance. Only a numerical project target or result is included in `environmental_metrics`.
10. Every evidence snippet is a continuous quotation found on its recorded PDF page after whitespace normalization.

These 12 files form a development set. They may be inspected when refining extraction logic and must not be used as an independent final benchmark.
