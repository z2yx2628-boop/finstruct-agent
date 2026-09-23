from typing import Literal

from pydantic import BaseModel, Field, model_validator


DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

CapacityEventType = Literal[
    "capacity_construction",
    "capacity_replacement",
    "technical_upgrade",
    "commissioning",
    "delay",
    "suspension",
    "termination",
    "maintenance",
]

DecisionReason = Literal[
    "trade_policy",          # tariffs, anti-dumping, quotas, CBAM, export policy
    "environmental_policy",  # ultra-low emission, carbon, energy-saving rules
    "industrial_policy",     # capacity replacement rules, industry regulation
    "market_demand",         # demand, prices, product structure
    "cost_reduction",        # cost, efficiency, raw materials
    "equipment_safety",      # ageing equipment, safety hazards
    "financing",             # funding, cash flow, fundraising progress
    "overseas_expansion",    # overseas market or resource access
    "other",
]

ProjectStatus = Literal[
    "planned",
    "approved",
    "under_construction",
    "commissioned",
    "delayed",
    "suspended",
    "terminated",
    "temporarily_shut_down",
]


class CapacityChange(BaseModel):
    action: Literal["new", "retired"]
    facility_type: str | None = None
    product_name: str | None = None
    capacity: float = Field(
        gt=0,
        description="保留公告原始数值，不进行单位换算",
    )
    capacity_unit: str = Field(min_length=1)
    source_page: int = Field(ge=1)
    evidence_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class EnvironmentalMetric(BaseModel):
    metric_type: Literal[
        "energy_consumption",
        "energy_saving",
        "carbon_emission",
        "carbon_reduction",
        "pollutant_emission",
        "pollutant_reduction",
    ]
    metric_name: str = Field(min_length=1)
    value: float = Field(ge=0)
    unit: str = Field(min_length=1)
    period: str | None = None
    source_page: int = Field(ge=1)
    evidence_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class CapacityEvent(BaseModel):
    event_type: CapacityEventType
    project_name: str | None = None
    project_entity: str | None = None
    project_location: str | None = None
    # V7 research fields: domestic vs overseas projects and stated motives.
    project_country: str | None = None
    decision_reasons: list[DecisionReason] = Field(default_factory=list)
    decision_reason_text: str | None = None
    project_status: ProjectStatus | None = None

    investment_amount: float | None = Field(default=None, ge=0)
    investment_unit: str | None = None
    investment_currency: str | None = None
    funding_source: str | None = None

    planned_start_date: str | None = Field(
        default=None,
        pattern=DATE_PATTERN,
    )
    planned_completion_date: str | None = Field(
        default=None,
        pattern=DATE_PATTERN,
    )
    commissioning_date: str | None = Field(
        default=None,
        pattern=DATE_PATTERN,
    )
    delay_until_date: str | None = Field(
        default=None,
        pattern=DATE_PATTERN,
    )
    timeline_text: str | None = None

    # V7: temporary production impact (maintenance, planned shutdown of a
    # facility during an upgrade, accident or weather halt). These are not
    # capacity changes and must not be recorded in capacity_changes.
    shutdown_facility: str | None = None
    shutdown_start_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    expected_restart_date: str | None = Field(default=None, pattern=DATE_PATTERN)
    shutdown_days: float | None = Field(default=None, gt=0)
    output_loss_amount: float | None = Field(default=None, gt=0)
    output_loss_unit: str | None = None
    output_loss_product: str | None = None

    technology_description: str | None = None
    project_purpose: str | None = None
    capacity_changes: list[CapacityChange] = Field(default_factory=list)
    environmental_metrics: list[EnvironmentalMetric] = Field(
        default_factory=list
    )

    source_page: int = Field(ge=1)
    evidence_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_investment_fields(self):
        if self.investment_amount is None:
            if self.investment_unit or self.investment_currency:
                raise ValueError(
                    "Investment unit or currency requires an amount"
                )
        elif not self.investment_unit:
            raise ValueError(
                "investment_unit is required when amount is present"
            )
        if self.output_loss_amount is not None and not self.output_loss_unit:
            raise ValueError(
                "output_loss_unit is required when output_loss_amount is present"
            )
        return self


class CapacityDocument(BaseModel):
    security_code: str | None = None
    security_name: str | None = None
    company_name: str | None = None
    announcement_number: str | None = None
    announcement_date: str | None = Field(
        default=None,
        pattern=DATE_PATTERN,
    )
    events: list[CapacityEvent] = Field(default_factory=list)