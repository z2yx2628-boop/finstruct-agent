import calendar
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

NON_PROJECT_CAPITAL_PATTERN = re.compile(
    r"注册资本|注册资金|授权资本|融资|担保|授信|额度|借款|贷款|"
    r"募集资金净额|募集资金总额|发行费用|资产总[计额]|净资产|总资产"
)

INVESTMENT_UNIT_SCALE = {
    "元": 1,
    "万元": 10_000,
    "亿元": 100_000_000,
    "美元": 1,
    "万美元": 10_000,
    "亿美元": 100_000_000,
}

FUNDING_SOURCE_PATTERN = re.compile(
    r"自有|自筹|募集|募投|贷款|融资|借款|银行|股东|超募|专项|债券|资本金|"
    r"政府|补助|补贴|出资|IPO|发行"
)

FRAMEWORK_PLAN_PATTERN = re.compile(
    r"投资框架计划|固定资产投资(?:年中)?计划|年度投资计划|投资计划(?:调整)?$"
)

CJK_SPACE_PATTERN = re.compile(
    r"(?<=[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef])\s+"
    r"|\s+(?=[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef])"
)

# V7: wording for a temporary production loss (maintenance, shutdown during
# an upgrade, accident or weather halt), as opposed to permanent retirement.
TEMPORARY_LOSS_PATTERN = re.compile(
    r"(?:停产|停炉|停机|检修|休风|焖炉|限产|减产).{0,30}?\d+(?:\.\d+)?\s*(?:天|日|个月)"
    r"|\d+(?:\.\d+)?\s*(?:天|日|个月).{0,20}?(?:停产|停炉|检修)"
    r"|(?:减少|影响|损失|降低).{0,15}?(?:产量|铁水量|钢产量)"
    r"|复产|恢复生产"
)
PERMANENT_RETIREMENT_PATTERN = re.compile(r"淘汰|拆除|去功能化|退出|关停|永久")
DURATION_DAYS = re.compile(r"(\d+(?:\.\d+)?)\s*天")


def is_temporary_output_loss(record: dict) -> bool:
    evidence = re.sub(r"\s+", "", record["evidence_text"])
    return bool(
        TEMPORARY_LOSS_PATTERN.search(evidence)
        and not PERMANENT_RETIREMENT_PATTERN.search(evidence)
    )


def move_loss_to_impact_fields(event: dict, record: dict) -> dict:
    """Record a temporary loss on the event instead of as a capacity change."""
    moved = {}
    if event.get("output_loss_amount") is None:
        unit = re.sub(r"/年$", "", record["capacity_unit"])
        moved = {
            "output_loss_amount": record["capacity"],
            "output_loss_unit": unit,
            "output_loss_product": record.get("product_name"),
        }
        if record.get("facility_type") and not event.get("shutdown_facility"):
            moved["shutdown_facility"] = record["facility_type"]
        days = DURATION_DAYS.search(re.sub(r"\s+", "", record["evidence_text"]))
        if days and event.get("shutdown_days") is None:
            moved["shutdown_days"] = float(days.group(1))
        event.update(moved)
    return moved


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
    "计划新增年产",
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
    "立方米/座",
    "㎡/台",
    "㎡",
    "平方米",
    "平方米/台",
    "t/座",
    "t",
    "吨",
    "吨/座",
    "mm/条",
    "毫米/条",
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

ACTUAL_COMMISSIONING_MARKERS = (
    "正式投产",
    "投入生产",
    "建成投运",
    "全线投产",
    "顺利出铁",
    "顺利出焦",
    "成功下线",
)

NON_COMMISSIONING_MARKERS = (
    "验收",
    "预计",
    "计划",
    "公告",
    "董事会",
)


MONETARY_UNIT_PATTERN = re.compile(
    r"^(?:人民币|美元|港元|欧元|日元)?(?:元|千元|万元|百万元|千万元|亿元|万美元|亿美元|美元)$"
)


def is_monetary_capacity_unit(unit: str | None) -> bool:
    if not unit:
        return False
    compact = re.sub(r"\s+", "", str(unit))
    return bool(MONETARY_UNIT_PATTERN.match(compact))


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
            elif is_monetary_capacity_unit(record.get("capacity_unit")):
                changes.append({
                    "event_index": event_index,
                    "record_index": record_index,
                    "action": "remove_monetary_capacity_change",
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


def source_date_variants(value: str) -> tuple[str, ...]:
    year, month, day = value.split("-")
    return (
        value,
        f"{year}年{int(month)}月{int(day)}日",
        f"{year}年{month}月{day}日",
    )

def exact_date_supported(value: str, full_text: str) -> bool:
    year, month, day = (int(part) for part in value.split("-"))
    compact_text = re.sub(r"\s+", "", full_text)

    if any(
        variant in compact_text
        for variant in source_date_variants(value)
    ):
        return True

    last_day = calendar.monthrange(year, month)[1]
    month_end_markers = (
        f"{year}年{month}月末",
        f"{year}年{month}月底",
    )
    return (
        day == last_day
        and any(marker in compact_text for marker in month_end_markers)
    )
def commissioning_date_supported(value: str, full_text: str) -> bool:
    segments = [
        re.sub(r"\s+", "", segment)
        for segment in re.split(r"[。；;\n]", re.sub(r"[ \t\u3000]+", "", full_text))
    ]
    variants = source_date_variants(value)
    dated_segments = [
        segment for segment in segments
        if any(variant in segment for variant in variants)
    ]
    if not dated_segments:
        return False
    for segment in dated_segments:
        if any(marker in segment for marker in NON_COMMISSIONING_MARKERS):
            continue
        dated_plain_commissioning = any(
            re.search(
                re.escape(variant) + r"(?:正式|顺利|成功)?投产(?!后)",
                segment,
            )
            for variant in variants
        )
        if dated_plain_commissioning or any(
            marker in segment for marker in ACTUAL_COMMISSIONING_MARKERS
        ):
            if (
                "全线" not in segment
                and re.search(r"预计.{0,30}全线.{0,20}投产", full_text)
            ):
                continue
            return True
    return False


def normalize_converter_spec(record: dict) -> dict | None:
    evidence = record["evidence_text"]
    multiplied = re.search(
        r"(\d+)\s*[×xX*]\s*(\d+(?:\.\d+)?)\s*[t吨]\s*转炉系统",
        evidence,
    )
    if multiplied:
        count, capacity = multiplied.groups()
        return {
            "facility_type": f"{count}×{capacity}t转炉系统",
            "product_name": None,
            "capacity": float(capacity),
            "capacity_unit": "t/座",
        }

    single = re.search(r"(?<![×xX*\d])(\d+(?:\.\d+)?)\s*[t吨]\s*转炉系统", evidence)
    if single:
        capacity = single.group(1)
        return {
            "facility_type": f"{capacity}t转炉系统",
            "product_name": None,
            "capacity": float(capacity),
            "capacity_unit": "t/座",
        }
    return None


def canonical_environmental_metric_name(metric: dict) -> str | None:
    name = metric["metric_name"]
    if (
        metric["metric_type"] == "carbon_reduction"
        and name in {"碳排放", "碳排放降低", "碳排放降低率"}
    ):
        return "碳减排率"
    if (
        metric["metric_type"] == "energy_saving"
        and name in {"固体燃耗", "固体燃耗降低", "固体燃耗降低率"}
    ):
        return "固体燃耗降低率"
    return None


def find_formal_aggregate_capacity(pages: list[dict]) -> dict | None:
    pattern = re.compile(
        r"(?:生产规模|新增产能|设计产能)(?:为|：|:)?"
        r"(?P<label>[^，。；;\d]{1,30}?)"
        r"(?P<capacity>\d+(?:,\d{3})*(?:\.\d+)?)\s*"
        r"(?P<unit>万吨/年|万吨|吨/年)"
    )
    for page in pages:
        match = pattern.search(page["text"])
        if not match:
            continue
        label = match.group("label").strip(" ，、：:")
        product_name = (
            label if label.endswith("产能") else f"{label}产能"
        )
        return {
            "action": "new",
            "facility_type": label or None,
            "product_name": product_name or None,
            "capacity": float(match.group("capacity").replace(",", "")),
            "capacity_unit": match.group("unit"),
            "source_page": page["page"],
            "evidence_text": match.group(0),
            "confidence": 1.0,
        }
    return None


def has_matching_capacity_record(event: dict, candidate: dict) -> bool:
    return any(
        record["action"] == candidate["action"]
        and record["capacity"] == candidate["capacity"]
        and record["capacity_unit"] == candidate["capacity_unit"]
        for record in event["capacity_changes"]
    )


def investment_unit_forms(amount: float, unit: str) -> list[tuple[float, str]]:
    forms = [(amount, unit)]
    scale = INVESTMENT_UNIT_SCALE.get(unit)
    if scale is None:
        return forms
    currency_suffix = "美元" if unit.endswith("美元") else "元"
    for other_unit, other_scale in INVESTMENT_UNIT_SCALE.items():
        if other_unit == unit or not other_unit.endswith(currency_suffix):
            continue
        if currency_suffix == "元" and other_unit.endswith("美元"):
            continue
        converted = round(amount * scale / other_scale, 6)
        forms.append((converted, other_unit))
    return forms


def number_positions(value: float, text: str) -> list[int]:
    expected = f"{value:.6f}".rstrip("0").rstrip(".")
    positions = []
    for match in re.finditer(r"(?<![\d.])\d[\d,]*(?:\.\d+)?(?![\d.])", text):
        candidate = match.group(0).replace(",", "")
        try:
            if float(candidate) == float(expected):
                positions.append(match.start())
        except ValueError:
            continue
    return positions


def keep_number_breaks(text: str) -> str:
    """Remove whitespace but keep one space between two digits, so adjacent table cells
    ("8,000.00  6,000.00") do not glue into one number ("8,000.006,000.00")."""
    def replace(match: re.Match) -> str:
        before = text[match.start() - 1] if match.start() > 0 else ""
        after = text[match.end()] if match.end() < len(text) else ""
        return " " if before.isdigit() and after.isdigit() else ""

    return re.sub(r"\s+", replace, text)


def find_supported_investment(
    amount: float,
    unit: str,
    text: str,
) -> tuple[float, str] | None:
    """Return the source form of a project investment, or None.

    The amount must appear in the source with its unit (or an equivalent
    万/亿 unit). It is rejected when the text right before every occurrence
    describes registered capital, financing, guarantees, loans, raised funds
    or balance-sheet totals rather than a project investment.
    """
    compact_text = keep_number_breaks(text)
    for form_amount, form_unit in investment_unit_forms(amount, unit):
        for position in number_positions(form_amount, compact_text):
            tail = compact_text[position:position + 30]
            number_text = re.match(r"[\d,.]+", tail).group(0)
            after = compact_text[
                position + len(number_text):
                position + len(number_text) + len(form_unit) + 2
            ]
            unit_nearby = form_unit in after
            if not unit_nearby:
                segment_start = max(
                    compact_text.rfind(mark, 0, position)
                    for mark in ("。", "；", ";")
                )
                segment_end_candidates = [
                    index for index in (
                        compact_text.find(mark, position)
                        for mark in ("。", "；", ";")
                    ) if index >= 0
                ]
                segment_end = min(segment_end_candidates, default=len(compact_text))
                segment = compact_text[segment_start + 1:segment_end]
                unit_nearby = (
                    re.search(rf"单位[:：](?:人民币)?{re.escape(form_unit)}", segment) is not None
                    or f"（{form_unit}）" in segment
                    or f"({form_unit})" in segment
                )
            if not unit_nearby:
                continue
            window = compact_text[max(0, position - 40):position]
            if NON_PROJECT_CAPITAL_PATTERN.search(window):
                continue
            return form_amount, form_unit
    return None


def explicit_project_investment_supported(
    amount: float,
    unit: str,
    text: str,
) -> bool:
    return find_supported_investment(amount, unit, text) is not None


COUNTRY_MARKERS = (
    ("印度尼西亚", "印度尼西亚"), ("印尼", "印度尼西亚"), ("马来西亚", "马来西亚"),
    ("越南", "越南"), ("泰国", "泰国"), ("沙特", "沙特阿拉伯"), ("塞尔维亚", "塞尔维亚"),
    ("墨西哥", "墨西哥"), ("巴西", "巴西"), ("印度", "印度"), ("津巴布韦", "津巴布韦"),
    ("南非", "南非"), ("埃及", "埃及"), ("阿联酋", "阿联酋"), ("土耳其", "土耳其"),
    ("美国", "美国"), ("德国", "德国"), ("法国", "法国"), ("意大利", "意大利"),
    ("英国", "英国"), ("俄罗斯", "俄罗斯"), ("哈萨克斯坦", "哈萨克斯坦"),
    ("菲律宾", "菲律宾"), ("马来", "马来西亚"), ("柬埔寨", "柬埔寨"),
)
CHINA_LOCATION = re.compile(
    r"省|自治区|开发区|工业园|中国|北京|上海|天津|重庆"
    r"|[\u4e00-\u9fff]{2,}(?:市|县|镇)"
    # "区" only after a place name, not generic 厂区/园区/库区/矿区 ("现有厂区").
    r"|[\u4e00-\u9fff]{2,}(?<![厂园库矿])区"
)


def infer_project_country(location: str | None) -> str | None:
    """Country from an explicit location; None when the text is unclear."""
    if not location:
        return None
    compact = re.sub(r"\s+", "", location)
    for marker, country in COUNTRY_MARKERS:
        if marker in compact:
            return country
    if CHINA_LOCATION.search(compact):
        return "中国"
    return None


def collapse_cjk_spaces(value: str | None) -> str | None:
    if value is None:
        return None
    return CJK_SPACE_PATTERN.sub("", value).strip()


def is_framework_plan_event(event: dict) -> bool:
    return bool(
        event["project_name"]
        and FRAMEWORK_PLAN_PATTERN.search(
            re.sub(r"\s+", "", event["project_name"])
        )
    )


def merge_framework_plan_items(
    events: list[dict],
    changes: list[dict],
) -> list[dict]:
    """Keep one aggregate event when an annual investment plan is present."""
    framework_indexes = [
        index for index, event in enumerate(events)
        if is_framework_plan_event(event)
    ]
    if not framework_indexes:
        return events
    keep = framework_indexes[0]
    kept_events = []
    for index, event in enumerate(events):
        if index == keep or event["event_type"] in {
            "delay", "suspension", "termination",
        }:
            kept_events.append(event)
            continue
        changes.append({
            "event_index": index,
            "action": "merge_framework_plan_item",
            "original": event["project_name"],
        })
    return kept_events


def is_planned_capacity_of_adverse_project(
    event: dict,
    record: dict,
) -> bool:
    if (
        event["event_type"] not in {"termination", "suspension", "delay"}
        or record["action"] != "new"
    ):
        return False
    evidence = re.sub(r"[\s,]", "", record["evidence_text"])
    name = re.sub(r"[\s,]", "", event["project_name"] or "")
    capacity_text = f"{record['capacity']:g}"
    in_name = capacity_text in name and re.search(r"年(?:产|加工)", name)
    in_named_project = re.search(
        r"年(?:产|加工)" + re.escape(capacity_text) + r".{0,40}?项目",
        evidence,
    )
    return bool(in_name or in_named_project)


def breakdown_record_indexes(records: list[dict]) -> set[int]:
    """Indexes of component records whose values sum to another record."""
    indexes: set[int] = set()
    for total_index, total in enumerate(records):
        components = [
            index for index, record in enumerate(records)
            if index != total_index
            and record["action"] == total["action"]
            and record["capacity_unit"] == total["capacity_unit"]
            and record["capacity"] < total["capacity"]
            and "其中" in record["evidence_text"]
        ]
        if len(components) < 2:
            continue
        component_sum = sum(records[index]["capacity"] for index in components)
        if abs(component_sum - total["capacity"]) <= 0.01 * total["capacity"]:
            indexes.update(components)
    return indexes


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

    for field in ("announcement_number", "company_name", "security_name"):
        value = data.get(field)
        collapsed = collapse_cjk_spaces(value)
        if value is not None and collapsed != value:
            data[field] = collapsed
            changes.append({
                "action": "collapse_cjk_spaces",
                "field": field,
                "original": value,
            })

    data["events"] = merge_project_replacement_events(
        data["events"],
        changes,
    )
    data["events"] = merge_framework_plan_items(data["events"], changes)

    for event_index, event in enumerate(data["events"]):
        if should_classify_as_technical_upgrade(event, full_text):
            event["event_type"] = "technical_upgrade"
            changes.append({
                "event_index": event_index,
                "action": "classify_existing_asset_technical_upgrade",
                "original": "capacity_construction",
                "normalized": "technical_upgrade",
            })

        formal_capacity = find_formal_aggregate_capacity(pages)
        if (
            formal_capacity is not None
            and len(data["events"]) == 1
            and event["event_type"] == "capacity_construction"
            and not has_matching_capacity_record(event, formal_capacity)
        ):
            event["capacity_changes"].append(formal_capacity)
            changes.append({
                "event_index": event_index,
                "action": "recover_formal_aggregate_capacity",
                "normalized": formal_capacity,
            })

        for field in ("project_name", "project_entity", "project_location"):
            value = event[field]
            collapsed = collapse_cjk_spaces(value)
            if value is not None and collapsed != value:
                event[field] = collapsed
                changes.append({
                    "event_index": event_index,
                    "action": "collapse_cjk_spaces",
                    "field": field,
                    "original": value,
                })

        if event.get("project_country") is None:
            country = infer_project_country(event["project_location"])
            if country is not None:
                event["project_country"] = country
                changes.append({
                    "event_index": event_index,
                    "action": "infer_project_country",
                    "normalized": country,
                })
        reason_text = event.get("decision_reason_text")
        if reason_text and not text_supported(reason_text, full_text):
            event["decision_reason_text"] = None
            changes.append({
                "event_index": event_index,
                "action": "clear_unsupported_reason_text",
                "original": reason_text,
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
        supported_investment = (
            find_supported_investment(amount, unit, full_text)
            if amount is not None
            else None
        )
        if supported_investment is not None and supported_investment != (
            amount, unit,
        ):
            event["investment_amount"], event["investment_unit"] = (
                supported_investment
            )
            changes.append({
                "event_index": event_index,
                "action": "restore_source_investment_unit",
                "original": {"investment_amount": amount, "investment_unit": unit},
                "normalized": {
                    "investment_amount": supported_investment[0],
                    "investment_unit": supported_investment[1],
                },
            })
        funding_source = event["funding_source"]
        if funding_source and not FUNDING_SOURCE_PATTERN.search(funding_source):
            event["funding_source"] = None
            changes.append({
                "event_index": event_index,
                "action": "clear_non_source_funding_text",
                "original": funding_source,
            })
        if amount is not None and supported_investment is None:
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
        for field in (
            "planned_start_date",
            "planned_completion_date",
            "delay_until_date",
        ):
            value = event[field]
            if value is not None and not exact_date_supported(
                value,
                full_text,
            ):
                event[field] = None
                changes.append({
                    "event_index": event_index,
                    "action": "clear_unsupported_exact_date",
                    "field": field,
                    "original": value,
                }) 
        commissioning_date = event["commissioning_date"]
        if (
            commissioning_date is not None
            and not commissioning_date_supported(
                commissioning_date,
                full_text,
            )
        ):
            event["commissioning_date"] = None
            changes.append({
                "event_index": event_index,
                "action": "clear_unsupported_commissioning_date",
                "original": commissioning_date,
            })

        framework_event = is_framework_plan_event(event)
        breakdown_indexes = breakdown_record_indexes(event["capacity_changes"])
        for record in event["capacity_changes"]:
            for field in ("facility_type", "product_name"):
                record[field] = collapse_cjk_spaces(record[field])

        kept_capacity_changes = []
        for record_index, record in enumerate(event["capacity_changes"]):
            removal_action = None
            if is_temporary_output_loss(record):
                removal_action = "move_temporary_loss_to_impact"
                moved = move_loss_to_impact_fields(event, record)
                if moved:
                    changes.append({
                        "event_index": event_index,
                        "action": "set_temporary_impact_fields",
                        "normalized": moved,
                    })
            elif framework_event:
                removal_action = "remove_framework_item_capacity"
            elif record_index in breakdown_indexes:
                removal_action = "remove_capacity_breakdown"
            elif is_planned_capacity_of_adverse_project(event, record):
                removal_action = "remove_planned_capacity_of_adverse_project"
            elif is_existing_asset_background(record):
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

            if event["event_type"] == "capacity_replacement":
                normalized_spec = normalize_converter_spec(record)
                if normalized_spec is not None:
                    original = {
                        field: record[field]
                        for field in normalized_spec
                    }
                    record.update(normalized_spec)
                    if original != normalized_spec:
                        changes.append({
                            "event_index": event_index,
                            "record_index": record_index,
                            "action": "normalize_converter_spec",
                            "original": original,
                            "normalized": normalized_spec,
                        })

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
                canonical_name = canonical_environmental_metric_name(metric)
                if (
                    canonical_name is not None
                    and canonical_name != metric["metric_name"]
                ):
                    original_name = metric["metric_name"]
                    metric["metric_name"] = canonical_name
                    changes.append({
                        "event_index": event_index,
                        "record_index": metric_index,
                        "action": "normalize_environmental_metric_name",
                        "original": original_name,
                        "normalized": canonical_name,
                    })
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
