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


class VerificationDto(BaseModel):
    attempted: bool = False
    succeeded: bool = False
    message: str | None = None
    search_api: str | None = None
    resolved: int = 0
    ambiguous: int = 0
    unresolved: int = 0
    with_abstract: int = 0
    with_doi: int = 0


class ExtractionResultDto(BaseModel):
    paper_id: str
    extracted_at: datetime
    parser: str
    document: Document
    references: list[Reference] = Field(default_factory=list)
    summary: ExtractionSummaryDto
    verification: VerificationDto = Field(default_factory=VerificationDto)


# Notes
#
# The response carries the domain models directly rather than a parallel set of
# API shapes. Document and RawReference are already Pydantic and already the
# contract every later stage reads, so mirroring them here would create two
# definitions of the same thing that drift apart.
#
# The summary is computed on the way out, never stored. Every number in it is a
# count over the document and the reference list, so it cannot disagree with
# the data it describes. This is the same reason parse_quality is a property on
# RawReference rather than a field.
#
# unlinked_citation_count is the honest one. It counts markers found in the
# text that could not be attached to any bibliography entry, and surfacing it
# is the point: a visible gap is worth more than a silently dropped citation.
#
# References are returned as Reference rather than RawReference even though
# extraction alone cannot resolve anything. Checking them against the
# literature databases is part of producing a parse rather than a separate
# thing the user asks for, so the response carries one list whose entries know
# whether they were verified, instead of two lists the caller has to reconcile.
#
# VerificationDto describes what happened to that check as a whole. It is
# separate from the per-reference status because "we could not reach the
# databases" and "we checked and found nothing" are different facts, and
# collapsing them would let an outage read as forty missing references.
