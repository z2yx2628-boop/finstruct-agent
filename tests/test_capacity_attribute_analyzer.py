from src.capacity_attribute_analyzer import analyze_report


def test_analyzer_separates_narrative_and_fact_errors():
    report = {
        "documents": {
            "sample": {
                "field_mismatches": [
                    {
                        "record_type": "event",
                        "record_index": 0,
                        "field": "timeline_text",
                        "expected": "计划2027年投产",
                        "actual": "预计2027年建成",
                        "matched": False,
                        "canonical_matched": False,
                    },
                    {
                        "record_type": "event",
                        "record_index": 0,
                        "field": "investment_amount",
                        "expected": 14061,
                        "actual": None,
                        "matched": False,
                        "canonical_matched": False,
                    },
                ]
            }
        }
    }

    analysis = analyze_report(report)

    assert analysis["mismatch_count"] == 2
    assert analysis["by_category"] == {
        "narrative_wording_or_coverage": 1,
        "missing_value": 1,
    }
