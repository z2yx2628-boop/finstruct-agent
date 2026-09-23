"""External guarantee announcements (对外担保 / 为子公司提供担保).

Each event is one guarantor -> guaranteed-party relationship disclosed as a
decision in this announcement. These pairs become credit-risk edges in the
industry-chain graph: if the guaranteed party defaults, the guarantor pays.
"""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

GuaranteeEventType = Literal[
    "guarantee_provided",   # a guarantee contract signed / guarantee provided
    "guarantee_limit",      # an approved guarantee quota (年度担保额度预计)
    "guarantee_released",   # guarantee released, expired or terminated early
    "guarantee_overdue",    # overdue guarantee, compensation paid, litigation
]

Relationship = Literal[
    "wholly_owned_subsidiary",
    "controlled_subsidiary",
    "parent_or_controlling_shareholder",
    "sister_company",
    "associate_or_joint_venture",
    "other_related_party",
    "unrelated_party",
]

GuaranteeType = Literal[
    "joint_and_several",   # 连带责任保证
    "general",             # 一般保证
    "mortgage",            # 抵押
    "pledge",              # 质押
    "other",
]


class GuaranteeEvent(BaseModel):
    event_type: GuaranteeEventType
    guarantor: str = Field(min_length=1)
    guaranteed_party: str | None = None
    relationship: Relationship | None = None
    is_related_transaction: bool | None = None

    guarantee_amount: float | None = Field(default=None, gt=0)
    guarantee_unit: str | None = None
    guarantee_currency: str | None = None
    guarantee_type: GuaranteeType | None = None
    creditor: str | None = None
    guaranteed_debt_purpose: str | None = None

    start_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    end_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    period_text: str | None = None

    has_counter_guarantee: bool | None = None
    guaranteed_party_debt_ratio: float | None = Field(default=None, ge=0)

    source_page: int = Field(ge=1)
    evidence_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_amount(self):
        if self.guarantee_amount is None:
            if self.guarantee_unit or self.guarantee_currency:
                raise ValueError("Guarantee unit or currency requires an amount")
        elif not self.guarantee_unit:
            raise ValueError("guarantee_unit is required when amount is present")
        return self


class GuaranteeDocument(BaseModel):
    security_code: str | None = None
    security_name: str | None = None
    company_name: str | None = None
    announcement_number: str | None = None
    announcement_date: str | None = Field(default=None, pattern=DATE_PATTERN)

    # Cumulative position disclosed in the "累计对外担保" section.
    total_guarantee_balance: float | None = Field(default=None, ge=0)
    total_guarantee_unit: str | None = None
    total_guarantee_net_asset_ratio: float | None = Field(default=None, ge=0)
    external_guarantee_balance: float | None = Field(default=None, ge=0)
    external_guarantee_unit: str | None = None
    overdue_guarantee_amount: float | None = Field(default=None, ge=0)
    overdue_guarantee_unit: str | None = None

    events: list[GuaranteeEvent] = Field(default_factory=list)
