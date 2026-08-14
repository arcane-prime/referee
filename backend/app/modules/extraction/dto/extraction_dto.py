from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.document import Document
from app.domain.library import Reference


class ReferenceSummaryDto(BaseModel):
    total: int
    good: int
    degraded: int
    failed: int


class ExtractionSummaryDto(BaseModel):
    section_count: int
    block_count: int
    citation_count: int
    unlinked_citation_count: int
    references: ReferenceSummaryDto
    detected_style: str
    style_confidence: float


class ExtractionResultDto(BaseModel):
    paper_id: str
    extracted_at: datetime
    parser: str
    document: Document
    references: list[Reference] = Field(default_factory=list)
    summary: ExtractionSummaryDto
