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


# Notes
#
# A Sentence is derived at review time and never stored. It carries the block
# id, its index within that block, and the exact character offsets it occupies
# in that block's prose, plus the CiteNodes that fall inside it.
#
# Deriving rather than storing is what keeps findings anchored. The alternative
# is asking the model to return the claim it judged, which means findings point
# at paraphrased text that exists nowhere in the document, and the UI has
# nothing to highlight. Here every finding carries a block id and a span that
# came out of our own data structure, so the model cannot invent a location.
#
# Evidence is the anti-hallucination record for a support check. The model must
# produce a verbatim quote before it may assign a grade, and quote_verified
# records whether that quote was actually found in the abstract. A quote that
# fails verification forces the grade to insufficient_evidence, so a fabricated
# citation of evidence downgrades the finding instead of strengthening it.
#
# That check is deliberately code, not prompting. It makes the guarantee
# independent of which model is plugged in: a schema can force the shape of an
# answer, but only string matching can force the quote to be real.
#
# SuggestedSource.is_linkable and Finding.is_grounded encode the brief's
# hardest requirement, that every finding be grounded in something a reader can
# open. A missing-citation finding with no linkable source, or an unsupported
# claim with no verified quote, is not a finding worth showing.
#
# The three kinds make different claims, so they are grounded differently:
#
#   unsupported_claim  asserts a source fails to back a sentence, so it must
#                      carry a verified quote from that source
#   missing_citation   asserts specific work should have been cited, so it must
#                      carry a source the reader can open
#   uncited_claim      asserts only that a sentence states something factual
#                      and carries no citation at all
#
# The last needs no external grounding because it makes no external claim. It
# is an observation about the paper's own text, verifiable by reading the
# sentence, and it stays honest when literature search is unavailable: we can
# say "this assertion is unsupported" without pretending to know which work
# would support it. It becomes a missing_citation once a real candidate is
# found.
#
# Grades distinguish "the source contradicts this" from "the source does not
# address it". not_supported is a real problem; insufficient_evidence usually
# means the abstract was too short to tell, which is honest rather than
# alarming and should not be reported as if the author cited badly.
