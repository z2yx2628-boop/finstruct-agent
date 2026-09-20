import re

from schemas.capacity import CapacityDocument
from src.evidence_validator import number_supported, text_supported


PROJECT_INVESTMENT_MARKERS = (
    "项目总投资",
    "项目投资总额",
    "项目总投资额",
    "预计总投资",
    "计划总投资",
)


def sanitize_capacity_payload(data: dict) -> tuple[dict, list[dict]]:
    changes: list[dict] = []
    for event_index, event in enumerate(data.get("events", [])):
        capacity_changes = []
        for record_index, record in enumerate(
            event.get("capacity_changes") or []
        ):
            if (
                record.get("capacity") is None
                or not record.get("capacity_unit")
            ):
                changes.append({
                    "event_index": event_index,
                    "record_index": record_index,
                    "action": "remove_incomplete_capacity_change",
                    "original": record,
                })
            else:
                capacity_changes.append(record)
        event["capacity_changes"] = capacity_changes

        environmental_metrics = []
        for record_index, record in enumerate(
            event.get("environmental_metrics") or []
        ):
            if record.get("value") is None or not record.get("unit"):
                changes.append({
                    "event_index": event_index,
                    "record_index": record_index,
                    "action": "remove_incomplete_environmental_metric",
                    "original": record,
                })
            else:
                environmental_metrics.append(record)
        event["environmental_metrics"] = environmental_metrics
    return data, changes


def explicit_project_investment_supported(
    amount: float,
    unit: str,
    text: str,
) -> bool:
    segments = re.split(r"[。；;\n]", text)
    return any(
        number_supported(amount, segment)
        and text_supported(unit, segment)
        and any(marker in segment for marker in PROJECT_INVESTMENT_MARKERS)
        for segment in segments
    )


def normalize_capacity_fields(
    document: CapacityDocument,
    pages: list[dict],
) -> tuple[CapacityDocument, list[dict]]:
    data = document.model_dump()
    full_text = "\n".join(item["text"] for item in pages)
    changes: list[dict] = []

    for event_index, event in enumerate(data["events"]):
        project_name = event["project_name"]
        if (
            project_name is not None
            and not text_supported(project_name, full_text)
        ):
            event["project_name"] = None
            changes.append({
                "event_index": event_index,
                "action": "clear_unsupported_project_name",
                "original": project_name,
            })

        amount = event["investment_amount"]
        unit = event["investment_unit"]
        if amount is not None and not explicit_project_investment_supported(
            amount,
            unit,
            full_text,
        ):
            cleared_fields = (
                "investment_amount",
                "investment_unit",
                "investment_currency",
                "funding_source",
            )
            original = {
                field: event[field]
                for field in cleared_fields
                if event[field] is not None
            }
            for field in cleared_fields:
                event[field] = None
            changes.append({
                "event_index": event_index,
                "action": "clear_unsupported_investment",
                "original": original,
            })

        kept_metrics = []
        for metric_index, metric in enumerate(
            event["environmental_metrics"]
        ):
            evidence = metric["evidence_text"]
            supported = (
                number_supported(metric["value"], evidence)
                and text_supported(metric["unit"], evidence)
            )
            if supported:
                kept_metrics.append(metric)
            else:
                changes.append({
                    "event_index": event_index,
                    "record_index": metric_index,
                    "action": "remove_unsupported_environmental_metric",
                    "original": metric,
                })
        event["environmental_metrics"] = kept_metrics

    return CapacityDocument.model_validate(data), changes
