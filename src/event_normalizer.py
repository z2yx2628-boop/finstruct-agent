import re
from typing import Any

from schemas.pledge import PledgeDocument, PledgeEvent


SHARED_TEXT_FIELDS = ("pledgee",)


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value))


def same_table_group(first: PledgeEvent, second: PledgeEvent) -> bool:
    return (
        first.event_type == second.event_type
        and first.source_page == second.source_page
        and compact(first.shareholder_name) == compact(second.shareholder_name)
    )


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
