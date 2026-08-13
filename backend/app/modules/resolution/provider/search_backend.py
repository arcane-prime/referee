from typing import Protocol, runtime_checkable

from app.domain.library import SourceRecord


@runtime_checkable
class SearchBackend(Protocol):
    name: str

    async def find_by_doi(self, doi: str) -> SourceRecord | None:
        ...

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        ...


@runtime_checkable
class AbstractBackend(Protocol):
    name: str

    async def find_abstract(self, doi: str | None, title: str | None) -> str | None:
        ...


# Notes
#
# Two narrow interfaces rather than one wide one, because the two jobs have
# different owners. OpenAlex answers "does this work exist and what is it";
# Semantic Scholar is only asked for an abstract when OpenAlex has none.
#
# Splitting them keeps the fallback honest. If AbstractBackend were folded into
# SearchBackend, it would be tempting to let a second source also propose
# matches, and then two databases would be voting on identity with no shared
# scoring. One source decides what a reference is; the other only fills a gap
# in what that source returned.
#
# Both return domain objects, never raw JSON. Every provider that implements
# these owns its own mapping into SourceRecord, so the matcher and the
# orchestrator never learn the shape of anybody's API.
#
# This is the same seam as ParserBackend in extraction, and it exists for the
# same reason: the scoring logic downstream can then be tested against
# hand-written SourceRecords in milliseconds, with no network anywhere.
