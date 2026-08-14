from typing import Literal

from pydantic import BaseModel, Field

from app.domain.document import CiteNode


class Sentence(BaseModel):
    block_id: str
    index: int
    text: str
    start: int
    end: int
    cite_nodes: list[CiteNode] = Field(default_factory=list)

    @property
    def is_cited(self) -> bool:
        return any(node.ref_ids for node in self.cite_nodes)

    @property
    def ref_ids(self) -> list[str]:
        seen: list[str] = []
        for node in self.cite_nodes:
            for ref_id in node.ref_ids:
                if ref_id not in seen:
                    seen.append(ref_id)
        return seen


SupportGrade = Literal[
    "supports",
    "partially_supports",
    "not_supported",
    "insufficient_evidence",
]


class Evidence(BaseModel):
    ref_id: str
    quote: str | None = None
    grade: SupportGrade = "insufficient_evidence"
    note: str | None = None
    quote_verified: bool = False
    source_title: str | None = None
    source_doi: str | None = None
    source_url: str | None = None


class SuggestedSource(BaseModel):
    title: str
    doi: str | None = None
    openalex_id: str | None = None
    url: str | None = None
    year: int | None = None
    abstract: str | None = None
    reason: str | None = None

    @property
    def is_linkable(self) -> bool:
        return bool(self.doi or self.openalex_id or self.url)


FindingKind = Literal["unsupported_claim", "missing_citation", "uncited_claim"]
FindingSeverity = Literal["high", "medium", "low"]


class Finding(BaseModel):
    id: str
    kind: FindingKind
    severity: FindingSeverity = "medium"

    block_id: str
    sentence_index: int
    start: int
    end: int
    sentence: str

    message: str
    evidence: list[Evidence] = Field(default_factory=list)
    suggested_sources: list[SuggestedSource] = Field(default_factory=list)

    @property
    def is_grounded(self) -> bool:
        if self.kind == "unsupported_claim":
            return any(item.quote_verified for item in self.evidence)
        if self.kind == "missing_citation":
            return any(source.is_linkable for source in self.suggested_sources)
        return True
