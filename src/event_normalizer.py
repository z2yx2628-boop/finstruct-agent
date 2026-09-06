import re
from typing import Any

from schemas.pledge import PledgeDocument, PledgeEvent


SHARED_TEXT_FIELDS = ("pledgee",)
RELEASE_ONLY_BOOLEAN_FIELDS = (
    "is_restricted_share",
    "is_supplementary_pledge",
)
DATE_ONLY_PATTERN = re.compile(
    r"^\s*\d{4}\s*(?:[-/.]|年)\s*\d{1,2}\s*(?:[-/.]|月)\s*\d{1,2}\s*日?\s*$"
)


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value))


def same_table_group(first: PledgeEvent, second: PledgeEvent) -> bool:
    return (
        first.event_type == second.event_type
        and first.source_page == second.source_page
        and compact(first.shareholder_name) == compact(second.shareholder_name)
    )


def is_date_only(value: str | None) -> bool:
    return bool(value and DATE_ONLY_PATTERN.fullmatch(value))


def clear_semantic_conflicts(
    document: PledgeDocument,
) -> tuple[PledgeDocument, list[dict]]:
    """Clear values that conflict with the event field semantics."""
    normalized = document.model_copy(deep=True)
    changes = []

    def clear(index: int, event: PledgeEvent, field: str, reason: str) -> None:
        previous_value = getattr(event, field)
        if previous_value is None:
            return
        setattr(event, field, None)
        changes.append({
            "event_index": index,
            "event_type": event.event_type,
            "field": field,
            "previous_value": previous_value,
            "value": None,
            "reason": reason,
        })

    for index, event in enumerate(normalized.events):
        if event.event_type == "release":
            for field in RELEASE_ONLY_BOOLEAN_FIELDS:
                clear(
                    index,
                    event,
                    field,
                    "release_event_does_not_define_pledge_boolean",
                )

            if (
                event.pledge_end_date is not None
                and event.pledge_end_date == event.release_date
            ):
                clear(
                    index,
                    event,
                    "pledge_end_date",
                    "release_date_duplicated_as_pledge_end_date",
                )

        if (
            event.event_type == "extension"
            and is_date_only(event.pledge_end_condition)
        ):
            clear(
                index,
                event,
                "pledge_end_condition",
                "date_misclassified_as_pledge_end_condition",
            )

    return normalized, changes


def inherit_shared_table_values(
    document: PledgeDocument,
) -> tuple[PledgeDocument, list[dict]]:
    """Fill evidenced values from adjacent rows affected by merged cells."""
    normalized = document.model_copy(deep=True)
    changes = []

    for index, event in enumerate(normalized.events):
        for field in SHARED_TEXT_FIELDS:
            if getattr(event, field) is not None:
                continue

            neighbors = []
            for neighbor_index in (index - 1, index + 1):
                if neighbor_index < 0 or neighbor_index >= len(normalized.events):
                    continue
                neighbor = normalized.events[neighbor_index]
                value = getattr(neighbor, field)
                if value is not None and same_table_group(event, neighbor):
                    neighbors.append((neighbor_index, value))

            distinct_values = {
                compact(value): value for _, value in neighbors
            }
            if len(distinct_values) != 1:
                continue

            value = next(iter(distinct_values.values()))
            if compact(value) not in compact(event.evidence_text):
                continue

            source_event_index = next(
                neighbor_index
                for neighbor_index, neighbor_value in neighbors
                if compact(neighbor_value) == compact(value)
            )
            setattr(event, field, value)
            changes.append({
                "event_index": index,
                "event_type": event.event_type,
                "field": field,
                "value": value,
                "source_event_index": source_event_index,
                "reason": "adjacent_merged_cell_with_exact_evidence",
            })

    return normalized, changes


def normalize_event_fields(
    document: PledgeDocument,
) -> tuple[PledgeDocument, list[dict]]:
    normalized, semantic_changes = clear_semantic_conflicts(document)
    normalized, inherited_changes = inherit_shared_table_values(normalized)
    return normalized, [*semantic_changes, *inherited_changes]
