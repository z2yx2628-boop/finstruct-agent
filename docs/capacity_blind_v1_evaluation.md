# Capacity blind-set V1 evaluation

## Frozen inputs

- Prediction system commit: `0b8b73247a3c11030c09cae14a227ce73c1679d4`
- Prediction freeze commit: `442cb2c`
- Gold freeze commit: `7cfb37e`
- Prompt: `prompts/capacity_extraction_v4.txt`
- Model: `qwen-plus`
- Corpus: 8 documents, 9 gold events
- Prediction run count: 1

The predictions were generated before the gold files existed. The eight gold
files were produced from source PDFs without opening the frozen prediction
JSON files, hashed, documented and committed before this evaluation.

## Headline results

| Metric | Result |
| --- | ---: |
| Documents evaluated | 8/8 |
| Event precision / recall / F1 | 100.00% / 77.78% / 87.50% |
| Capacity-record precision / recall / F1 | 36.36% / 100.00% / 53.33% |
| Document-field accuracy | 38/40 (95.00%) |
| Factual-attribute accuracy | 122/151 (80.79%) |
| Factual overfills | 4 |
| Narrative strict accuracy | 4/21 (19.05%) |
| All attributes with safe canonical formatting | 126/172 (73.26%) |

Environmental-record precision, recall and F1 are displayed as 100% because
both gold and predictions contain zero environmental records. This is a
vacuous `0/0` result and must not be presented as evidence of environmental
metric extraction quality.

## Error concentration

1. The two annual technical-upgrade framework announcements were returned
   without events. This accounts for the two event false negatives and lowers
   event recall to 77.78%.
2. All four gold capacity records were detected, but seven extra equipment
   specifications were emitted as capacity records. Five occur in the Qingdao
   Special Steel continuation project and two in the Daye Special Steel
   upgrade. This is the main reason capacity-record precision is only 36.36%.
3. The delay announcement correctly produced two events, but total investment,
   funding source and several timeline fields were missed or represented
   inconsistently.
4. The Indonesia coke project was detected, but investment unit, project
   entity, funding source and several descriptive fields differed from the
   gold labels.
5. Two document-field errors are punctuation normalization differences in
   announcement numbers rather than entity-recognition failures.
6. Narrative strict accuracy is intentionally harsh because summaries must
   match character-for-character. It is useful for reproducibility but should
   not be treated as the primary factual quality metric.

## Interpretation

This blind result is materially weaker than the 12-document development score
and therefore rejects the assumption that the V4 extractor is already ready
for production or competition-wide claims. The current system is a validated
prototype with reliable document identification and good event precision, but
with insufficient event recall for framework announcements and substantial
capacity over-extraction on equipment-heavy project descriptions.

The sample remains small and was labeled by one annotator. Before using these
numbers in a submission, a second annotator should independently adjudicate
the material judgments listed in `data/gold/capacity_blind/README.md`. Any
adjudicated change must create a new gold version; this V1 baseline and report
must remain unchanged.

## Next development gate

Do not tune V4 directly against these eight blind labels. Create a new
development set containing at least:

- annual framework plans with many subprojects;
- equipment-heavy construction and upgrade announcements;
- multi-project delay announcements;
- overseas projects with mixed currencies and financing structures.

Develop V5 on that new set, then evaluate it on a separate untouched holdout.
The V1 blind score remains the honest baseline.
