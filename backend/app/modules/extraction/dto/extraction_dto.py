from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.document import Document
from app.domain.library import RawReference


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
    references: list[RawReference] = Field(default_factory=list)
    summary: ExtractionSummaryDto


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
