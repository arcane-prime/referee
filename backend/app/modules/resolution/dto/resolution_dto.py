from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.library import Reference


class ResolutionSummaryDto(BaseModel):
    total: int
    resolved: int
    ambiguous: int
    unresolved: int
    with_abstract: int
    with_doi: int


class ResolutionResultDto(BaseModel):
    paper_id: str
    resolved_at: datetime
    search_api: str
    abstract_api: str | None = None
    references: list[Reference] = Field(default_factory=list)
    summary: ResolutionSummaryDto


# Notes
#
# The summary is the honest-reporting surface for this stage. resolved,
# ambiguous and unresolved are reported separately rather than collapsed into a
# success rate, because the three mean different things to a researcher:
# ambiguous needs a decision from them, unresolved may mean the reference is
# wrong, and conflating either with success would hide exactly what the brief
# asks us to surface.
#
# with_abstract is tracked separately from resolved because it is the number
# stage 3 actually depends on. A reference can be confidently identified and
# still have no abstract available, and review can only check claims against
# sources it can read.
#
# As in extraction, the response carries the domain models directly rather than
# a parallel set of API shapes, so there is one definition of a Reference
# rather than two that can drift.
