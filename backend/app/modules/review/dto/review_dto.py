from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.review import Finding


class ReviewSummaryDto(BaseModel):
    sentences_examined: int
    claims_with_citations: int
    citations_checked: int
    references_without_abstract: int
    findings_total: int
    unsupported_claims: int
    missing_citations: int


class ReviewResultDto(BaseModel):
    paper_id: str
    revision: int
    reviewed_at: datetime
    model: str
    findings: list[Finding] = Field(default_factory=list)
    summary: ReviewSummaryDto
