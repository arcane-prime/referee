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
    reviewed_at: datetime
    model: str
    findings: list[Finding] = Field(default_factory=list)
    summary: ReviewSummaryDto


# Notes
#
# references_without_abstract is the honesty field. Those references were
# skipped entirely, because judging whether a source supports a claim without
# reading the source is precisely the fabrication this design prevents.
# Reporting the number makes the gap visible instead of letting a partial
# review look complete.
#
# citations_checked alongside claims_with_citations tells the reader how much
# of the paper was actually examined. A review reporting two findings means
# something quite different if it checked forty citations than if it checked
# four.
#
# Findings are returned as domain models rather than a parallel API shape, as
# in the other stages, so there is one definition rather than two that drift.
