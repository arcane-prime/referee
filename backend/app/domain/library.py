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


# Notes
#
# A RawReference is a query, not the truth. GROBID hands over the string
# "Child et al., Generating long sequences with sparse transformers, 2019" plus
# whatever fields it managed to pull out of it. Whether that names a paper that
# actually exists is stage 2's job, which is why nothing here talks about
# resolution.
#
# Two rules hold throughout. `raw` is always populated, because an entry whose
# fields failed to parse is still useful: it can be shown to the user verbatim
# and sent to a search API as a single query string. Dropping an entry because
# parsing failed is the exact failure the brief prohibits.
#
# And nothing evaluative is stored. "Is this reference well parsed?" is an
# opinion about the extraction, fully determined by which fields came back, so
# it is a property rather than a field. Storing it would be duplicated state
# free to drift from the data it describes. This is also what lets the parse
# report be a pure function over the model with no plumbing of its own.
#
# `id` comes from the TEI xml:id, so "b12" becomes "ref_12". That is emission
# order, not the number printed in the paper: ref_12 is the thirteenth
# reference, not the paper's "[12]". Ids are opaque handles, and the number a
# reader sees is produced by citeproc at render time.
#
# Library is append-only across a paper's lifetime. Once a reference exists it
# is never deleted, even if the user rejects the edit that introduced it, so no
# revision can point at a reference that has gone missing.
#
# ---------------------------------------------------------------- resolution
#
# A RawReference is what extraction produced. A Reference is that same entry
# after stage 2 has tried to find it in a real database. The split is
# deliberate: extraction states what the page said, resolution states what is
# true, and the two are never conflated in one object.
#
# Resolution has three outcomes and all of them are useful:
#
#   resolved     we are confident this names a real, identified work
#   ambiguous    several plausible matches, or one that is not convincing
#                enough. The candidates are kept so the user can choose.
#   unresolved   nothing credible was found. Said plainly, not papered over.
#
# `reason` carries a short human explanation for whichever outcome occurred.
# An honest "no match above threshold" is worth more to a researcher than a
# confident wrong answer.
#
# Reference.csl is the single place downstream code should read bibliographic
# data from. It returns the matched record when resolved and falls back to our
# own parse otherwise, which is what decouples output quality from parser
# quality: a reference GROBID mangled can still come out correct if the
# database found it.
#
# `provenance` is the structural anti-hallucination guard rather than a label.
# In stage 4 the agent may only insert a citation pointing at a reference where
# can_be_cited_by_the_agent is true, meaning it came from an API and carries a
# real external id. A fabricated reference cannot satisfy that, no matter what
# the model writes.
#
# `abstract` is the reason this stage exists at all. A paper's PDF does not
# contain the abstracts of the works it cites, and stage 3 cannot check whether
# a source supports a claim without reading that source.
