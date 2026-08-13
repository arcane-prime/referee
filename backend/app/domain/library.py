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


class Library(BaseModel):
    paper_id: str
    references: list[RawReference] = Field(default_factory=list)

    def get(self, ref_id: str) -> RawReference | None:
        return next((ref for ref in self.references if ref.id == ref_id), None)

    @property
    def ids(self) -> set[str]:
        return {ref.id for ref in self.references}


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
