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
    "purchase_raw_materials",   # 采购原材料 (铁矿石、废钢、合金…)
    "purchase_fuel_power",      # 采购燃料和动力 (煤、焦炭、电、气、水)
    "purchase_goods_other",     # 采购其他商品、设备、备件
    "sell_goods",               # 销售产品、商品
    "receive_services",         # 接受劳务、服务 (运输、工程、检修…)
    "provide_services",         # 提供劳务、服务
    "lease",                    # 租入或租出
    "financial_services",       # 存款、贷款、票据等金融服务
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
    counterparty: str = Field(min_length=1)
    relationship: Relationship | None = None
    transaction_category: TransactionCategory
    category_text: str | None = None          # 原文类别，例如“向关联人购买燃料和动力”
    goods_or_services: str | None = None      # 原文交易内容，例如“铁矿石、焦炭”

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
