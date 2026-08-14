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
