from typing import Literal

from pydantic import BaseModel, Field

from app.domain.csl import CSLItem
from app.domain.geometry import BBox

ParseQuality = Literal["good", "degraded", "failed"]


class RawReference(BaseModel):
    id: str
    raw: str
    parsed: CSLItem | None = None
    coords: list[BBox] = Field(default_factory=list)

    @property
    def has_title(self) -> bool:
        return bool(self.parsed and self.parsed.title)

    @property
    def has_authors(self) -> bool:
        return bool(self.parsed and self.parsed.author)

    @property
    def has_year(self) -> bool:
        return bool(self.parsed and self.parsed.year)

    @property
    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.has_title:
            missing.append("title")
        if not self.has_authors:
            missing.append("authors")
        if not self.has_year:
            missing.append("year")
        return missing

    @property
    def parse_quality(self) -> ParseQuality:
        if not self.has_title:
            return "failed"
        if self.has_authors and self.has_year:
            return "good"
        return "degraded"


class ExternalIds(BaseModel):
    doi: str | None = None
    openalex: str | None = None
    semantic_scholar: str | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.doi or self.openalex or self.semantic_scholar)


class SourceRecord(BaseModel):
    csl: CSLItem
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    abstract: str | None = None
    source_api: str


class MatchScore(BaseModel):
    total: float
    title: float
    authors: float | None = None
    year: float | None = None


class MatchCandidate(BaseModel):
    record: SourceRecord
    score: MatchScore


ResolutionStatus = Literal["resolved", "ambiguous", "unresolved"]


class Resolution(BaseModel):
    status: ResolutionStatus = "unresolved"
    score: float = 0.0
    matched: CSLItem | None = None
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    abstract: str | None = None
    source_api: str | None = None
    abstract_source: str | None = None
    reason: str | None = None
    candidates: list[MatchCandidate] = Field(default_factory=list)


Provenance = Literal["parsed_from_pdf", "fetched_from_api"]


class Reference(BaseModel):
    id: str
    raw: str
    parsed: CSLItem | None = None
    coords: list[BBox] = Field(default_factory=list)

    resolution: Resolution = Field(default_factory=Resolution)
    provenance: Provenance = "parsed_from_pdf"
    discovered_by: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.resolution.status == "resolved"

    @property
    def has_abstract(self) -> bool:
        return bool(self.resolution.abstract)

    @property
    def doi(self) -> str | None:
        return self.resolution.external_ids.doi

    @property
    def csl(self) -> CSLItem | None:
        if self.is_resolved and self.resolution.matched is not None:
            return self.resolution.matched
        return self.parsed

    @property
    def can_be_cited_by_the_agent(self) -> bool:
        return (
            self.provenance == "fetched_from_api"
            and not self.resolution.external_ids.is_empty
        )

    @classmethod
    def from_raw(cls, raw_reference: RawReference) -> "Reference":
        return cls(
            id=raw_reference.id,
            raw=raw_reference.raw,
            parsed=raw_reference.parsed,
            coords=raw_reference.coords,
        )


class Library(BaseModel):
    paper_id: str
    references: list[Reference] = Field(default_factory=list)

    def get(self, ref_id: str) -> Reference | None:
        return next((ref for ref in self.references if ref.id == ref_id), None)

    @property
    def ids(self) -> set[str]:
        return {ref.id for ref in self.references}

    @property
    def dois(self) -> set[str]:
        return {ref.doi.lower() for ref in self.references if ref.doi}
