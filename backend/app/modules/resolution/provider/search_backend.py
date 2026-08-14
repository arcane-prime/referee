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
