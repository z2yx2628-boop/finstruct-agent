from pydantic import BaseModel, Field


class PledgeRecord(BaseModel):
    shareholder_name: str | None = None
    pledged_shares: float | None = Field(default=None, ge=0)
    pledged_shares_unit: str | None = None
    pledge_start_date: str | None = None
    pledge_end_date: str | None = None
    pledgee: str | None = None
    shareholder_holding_ratio: float | None = Field(
        default=None, ge=0, le=100
    )
    total_share_capital_ratio: float | None = Field(
        default=None, ge=0, le=100
    )
    pledge_purpose: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    evidence_text: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class PledgeDocument(BaseModel):
    security_code: str | None = None
    security_name: str | None = None
    announcement_number: str | None = None
    company_name: str | None = None
    records: list[PledgeRecord] = Field(default_factory=list)