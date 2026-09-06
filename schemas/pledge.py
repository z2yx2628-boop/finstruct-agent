from typing import Literal

from pydantic import BaseModel, Field, model_validator


EventType = Literal["pledge", "release", "extension"]
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class PledgeEvent(BaseModel):
    event_type: EventType = Field(
        description="事件类型：新增质押、解除质押或质押展期"
    )
    shareholder_name: str = Field(min_length=1)
    shares: float = Field(
        gt=0,
        description="事件涉及的股份数量，不得换算原文单位",
    )
    shares_unit: str = Field(min_length=1)
    shareholder_holding_ratio: float | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    total_share_capital_ratio: float | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    is_restricted_share: bool | None = None
    is_supplementary_pledge: bool | None = None
    pledge_start_date: str | None = Field(
        default=None,
        pattern=DATE_PATTERN,
    )
    pledge_end_date: str | None = Field(
        default=None,
        pattern=DATE_PATTERN,
    )
    pledge_end_condition: str | None = None
    release_date: str | None = Field(
        default=None,
        pattern=DATE_PATTERN,
    )
    original_end_date: str | None = Field(
        default=None,
        pattern=DATE_PATTERN,
    )
    extended_end_date: str | None = Field(
        default=None,
        pattern=DATE_PATTERN,
    )
    pledgee: str | None = None
    purpose: str | None = None
    source_page: int = Field(ge=1)
    evidence_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class PledgeDocument(BaseModel):
    security_code: str | None = None
    security_name: str | None = None
    announcement_number: str | None = None
    company_name: str | None = None
    events: list[PledgeEvent] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_records(cls, value):
        if not isinstance(value, dict) or "events" in value:
            return value

        records = value.get("records")
        if not isinstance(records, list):
            return value

        migrated = dict(value)
        migrated.pop("records", None)
        migrated["events"] = []

        for record in records:
            if not isinstance(record, dict):
                migrated["events"].append(record)
                continue

            event = dict(record)
            event.setdefault("event_type", "pledge")
            event["shares"] = event.pop("pledged_shares", None)
            event["shares_unit"] = event.pop("pledged_shares_unit", None)
            event["purpose"] = event.pop("pledge_purpose", None)
            migrated["events"].append(event)

        return migrated
