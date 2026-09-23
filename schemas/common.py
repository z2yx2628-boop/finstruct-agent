from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


SourceType = Literal[
    "pdf_text",
    "pdf_scan",
    "pdf_mixed",
    "image",
    "webpage",
    "word",
    "spreadsheet",
]


class ParsedPage(BaseModel):
    page: int = Field(ge=1)
    text: str = ""
    ocr_used: bool = False
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)
    tables: list[dict[str, Any]] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    document_id: str = Field(min_length=1)
    source_type: SourceType
    source_name: str = Field(min_length=1)
    source_path: str | None = None
    source_url: str | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pages: list[ParsedPage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_source_location(self):
        if not self.source_path and not self.source_url:
            raise ValueError("source_path or source_url is required")
        return self