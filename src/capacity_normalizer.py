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

EXPLICIT_RETIREMENT_MARKERS = (
    "淘汰",
    "退出",
    "关停",
    "拆除",
    "停产",
    "去功能化",
)

HYPOTHETICAL_OUTPUT_MARKERS = (
    "完全达产后",
    "整体建成投产后",
    "项目建成后",
    "建成投产后",
    "预计可年产",
    "将形成年产",
)

FORMAL_CAPACITY_MARKERS = (
    "生产规模",
    "新增产能",
    "年新增",
    "设计产能",
)

EQUIPMENT_SPEC_UNITS = {
    "m³/座",
    "m3/座",
    "m³",
    "m3",
    "立方米",
    "㎡/台",
    "㎡",
    "平方米",
    "t/座",
    "t",
    "吨",
    "mm/条",
    "mm",
    "毫米",
}

EQUIPMENT_COUNT_UNITS = {
    "台",
    "座",
    "条",
    "套",
}

TECHNICAL_UPGRADE_MARKERS = (
    "成熟技术移植",
    "技术移植",
    "工艺改造",
    "系统改造",
    "升级改造",
    "大修",
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
    segments = re.split(r"[。；;]", text)
    return any(
        number_supported(amount, segment)
        and text_supported(unit, segment)
        and any(
            marker in re.sub(r"\s+", "", segment)
            for marker in PROJECT_INVESTMENT_MARKERS
        )
        for segment in segments
    )


def is_regulatory_environmental_threshold(
    evidence: str,
    page_text: str,
) -> bool:
    if not any(marker in evidence for marker in ("不高于", "不得超过")):
        return False
    compact_page = re.sub(r"\s+", "", page_text)
    compact_evidence = re.sub(r"\s+", "", evidence)
    evidence_index = compact_page.find(compact_evidence)
    if evidence_index < 0:
        return False
    context = compact_page[max(0, evidence_index - 180):evidence_index]
    return (
        "根据《" in context
        and any(marker in context for marker in ("要求", "规定", "明确"))
    )


def is_existing_asset_background(record: dict) -> bool:
    evidence = record["evidence_text"]
    return (
        record["action"] == "retired"
        and "现有" in evidence
        and not any(
            marker in evidence for marker in EXPLICIT_RETIREMENT_MARKERS
        )
    )


def is_hypothetical_capacity_for_adverse_event(
    event_type: str,
    record: dict,
) -> bool:
    return (
        event_type in {"termination", "suspension", "delay"}
        and record["action"] == "new"
        and any(
            marker in record["evidence_text"]
            for marker in HYPOTHETICAL_OUTPUT_MARKERS
        )
    )


def is_nonreplacement_equipment_spec(
    event_type: str,
    record: dict,
) -> bool:
    return (
        event_type != "capacity_replacement"
        and record["capacity_unit"] in EQUIPMENT_SPEC_UNITS
    )


def has_formal_aggregate_capacity(event: dict, full_text: str) -> bool:
    in_records = any(
        record["action"] == "new"
        and any(
            marker in record["evidence_text"]
            for marker in FORMAL_CAPACITY_MARKERS
        )
        for record in event["capacity_changes"]
    )
    compact_text = re.sub(r"\s+", "", full_text)
    in_document = bool(re.search(
        r"生产规模(?:为|：|:)?.{0,40}?\d+(?:\.\d+)?万吨/年",
        compact_text,
    ))
    return in_records or in_document


def is_projected_product_breakdown(
    event: dict,
    record: dict,
    full_text: str,
) -> bool:
    projected_pages = {
        item["source_page"]
        for item in event["capacity_changes"]
        if any(
            marker in item["evidence_text"]
            for marker in HYPOTHETICAL_OUTPUT_MARKERS
        )
    }
    return (
        event["event_type"] == "capacity_construction"
        and record["action"] == "new"
        and has_formal_aggregate_capacity(event, full_text)
        and (
            record["source_page"] in projected_pages
            or any(
                marker in record["evidence_text"]
                for marker in HYPOTHETICAL_OUTPUT_MARKERS
            )
        )
        and not any(
            marker in record["evidence_text"]
            for marker in FORMAL_CAPACITY_MARKERS
        )
    )


def is_equipment_breakdown_beside_aggregate(
    event: dict,
    record: dict,
    full_text: str,
) -> bool:
    return (
        event["event_type"] == "capacity_construction"
        and record["action"] == "new"
        and record["capacity_unit"] in EQUIPMENT_COUNT_UNITS
        and has_formal_aggregate_capacity(event, full_text)
        and not any(
            marker in record["evidence_text"]
            for marker in FORMAL_CAPACITY_MARKERS
        )
    )


def should_classify_as_technical_upgrade(
    event: dict,
    full_text: str,
) -> bool:
    if event["event_type"] != "capacity_construction":
        return False
    marker_count = sum(
        marker in full_text for marker in TECHNICAL_UPGRADE_MARKERS
    )
    return marker_count >= 2


def capacity_record_key(record: dict) -> tuple:
    return (
        record["action"],
        record["facility_type"],
        record["product_name"],
        record["capacity"],
        record["capacity_unit"],
        record["source_page"],
    )


def merge_project_replacement_events(
    events: list[dict],
    changes: list[dict],
) -> list[dict]:
    primary_by_project = {
        event["project_name"]: index
        for index, event in enumerate(events)
        if event["project_name"]
        and event["event_type"] != "capacity_replacement"
    }
    merged_indexes = set()
    for event_index, event in enumerate(events):
        project_name = event["project_name"]
        primary_index = primary_by_project.get(project_name)
        if (
            event["event_type"] != "capacity_replacement"
            or primary_index is None
            or primary_index == event_index
        ):
            continue

        primary = events[primary_index]
        existing = {
            capacity_record_key(record)
            for record in primary["capacity_changes"]
        }
        for record in event["capacity_changes"]:
            key = capacity_record_key(record)
            if key not in existing:
                primary["capacity_changes"].append(record)
                existing.add(key)
        merged_indexes.add(event_index)
        changes.append({
            "event_index": event_index,
            "target_event_index": primary_index,
            "action": "merge_project_replacement_event",
            "project_name": project_name,
        })
    return [
        event
        for index, event in enumerate(events)
        if index not in merged_indexes
    ]


def normalize_capacity_fields(
    document: CapacityDocument,
    pages: list[dict],
) -> tuple[CapacityDocument, list[dict]]:
    data = document.model_dump()
    full_text = "\n".join(item["text"] for item in pages)
    page_map = {item["page"]: item["text"] for item in pages}
    changes: list[dict] = []

    data["events"] = merge_project_replacement_events(
        data["events"],
        changes,
    )

    for event_index, event in enumerate(data["events"]):
        if should_classify_as_technical_upgrade(event, full_text):
            event["event_type"] = "technical_upgrade"
            changes.append({
                "event_index": event_index,
                "action": "classify_existing_asset_technical_upgrade",
                "original": "capacity_construction",
                "normalized": "technical_upgrade",
            })

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

        kept_capacity_changes = []
        for record_index, record in enumerate(event["capacity_changes"]):
            removal_action = None
            if is_existing_asset_background(record):
                removal_action = "remove_existing_asset_background"
            elif is_hypothetical_capacity_for_adverse_event(
                event["event_type"],
                record,
            ):
                removal_action = "remove_hypothetical_adverse_capacity"
            elif is_nonreplacement_equipment_spec(
                event["event_type"],
                record,
            ):
                removal_action = "remove_nonreplacement_equipment_spec"
            elif is_projected_product_breakdown(
                event,
                record,
                full_text,
            ):
                removal_action = "remove_projected_product_breakdown"
            elif is_equipment_breakdown_beside_aggregate(
                event,
                record,
                full_text,
            ):
                removal_action = "remove_equipment_breakdown"

            if removal_action:
                changes.append({
                    "event_index": event_index,
                    "record_index": record_index,
                    "action": removal_action,
                    "original": record,
                })
                continue

            if (
                record["product_name"] is None
                and record["facility_type"]
                and record["facility_type"].endswith("产能")
            ):
                record["product_name"] = record["facility_type"]
                record["facility_type"] = None
                changes.append({
                    "event_index": event_index,
                    "record_index": record_index,
                    "action": "move_capacity_label_to_product",
                    "normalized": record["product_name"],
                })

            if (
                record["capacity_unit"] == "万吨"
                and "产能" in record["evidence_text"]
                and record["action"] == "retired"
            ):
                original_unit = record["capacity_unit"]
                record["capacity_unit"] = "万吨/年"
                changes.append({
                    "event_index": event_index,
                    "record_index": record_index,
                    "action": "normalize_annual_capacity_unit",
                    "original": original_unit,
                    "normalized": record["capacity_unit"],
                })
            kept_capacity_changes.append(record)
        event["capacity_changes"] = kept_capacity_changes

        kept_metrics = []
        for metric_index, metric in enumerate(
            event["environmental_metrics"]
        ):
            evidence = metric["evidence_text"]
            page_text = page_map.get(metric["source_page"], "")
            supported = (
                number_supported(metric["value"], evidence)
                and text_supported(metric["unit"], evidence)
            )
            regulatory_threshold = is_regulatory_environmental_threshold(
                evidence,
                page_text,
            )
            if supported and not regulatory_threshold:
                kept_metrics.append(metric)
            else:
                changes.append({
                    "event_index": event_index,
                    "record_index": metric_index,
                    "action": (
                        "remove_regulatory_environmental_threshold"
                        if regulatory_threshold
                        else "remove_unsupported_environmental_metric"
                    ),
                    "original": metric,
                })
        event["environmental_metrics"] = kept_metrics

    return CapacityDocument.model_validate(data), changes
