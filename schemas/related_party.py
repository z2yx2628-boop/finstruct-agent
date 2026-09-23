"""Daily related-party transaction estimates (日常关联交易预计).

Each record is one row of the "本次日常关联交易预计金额和类别" table: one
transaction category with one related party (as the table prints it). These
rows become trade edges in the industry-chain graph: who buys ore, coke,
power or services from whom, and who sells steel to whom, inside a group.
"""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

TransactionCategory = Literal[
    "purchase_goods",       # 采购商品、原材料、燃料和动力
    "sell_goods",           # 销售产品、商品
    "receive_services",     # 接受劳务、服务
    "provide_services",     # 提供劳务、服务
    "lease_in",             # 租入资产
    "lease_out",            # 租出资产
    "financial_services",   # 资金使用费、利息收入、存贷款等资金往来
    "other",
]

Relationship = Literal[
    "parent_or_controlling_shareholder",
    "sister_company",                  # 同一控制人控制的其他企业
    "associate_or_joint_venture",
    "other_related_party",
]


class RelatedTransaction(BaseModel):
    listed_company: str = Field(min_length=1)
    # None when the estimate table is by category only (no counterparty column).
    counterparty: str | None = None
    relationship: Relationship | None = None
    transaction_category: TransactionCategory
    category_text: str | None = None          # 原文类别，例如“采购商品”“接受劳务/服务”
    goods_or_services: str | None = None      # 原文列明的具体内容，例如“铁矿石、焦炭”

    estimated_amount: float | None = Field(default=None, ge=0)
    estimated_unit: str | None = None
    prior_year_actual_amount: float | None = Field(default=None, ge=0)
    prior_year_actual_unit: str | None = None
    currency: str | None = None

    source_page: int = Field(ge=1)
    evidence_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_units(self):
        if self.estimated_amount is not None and not self.estimated_unit:
            raise ValueError("estimated_unit is required when estimated_amount is present")
        if self.prior_year_actual_amount is not None and not self.prior_year_actual_unit:
            raise ValueError("prior_year_actual_unit is required when prior_year_actual_amount is present")
        return self


class RelatedPartyDocument(BaseModel):
    security_code: str | None = None
    security_name: str | None = None
    company_name: str | None = None
    announcement_number: str | None = None
    announcement_date: str | None = Field(default=None, pattern=DATE_PATTERN)

    estimate_year: int | None = Field(default=None, ge=2000, le=2100)
    total_estimated_amount: float | None = Field(default=None, ge=0)
    total_estimated_unit: str | None = None
    requires_shareholder_approval: bool | None = None

    transactions: list[RelatedTransaction] = Field(default_factory=list)
