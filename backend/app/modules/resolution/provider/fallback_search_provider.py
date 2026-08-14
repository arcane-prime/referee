from app.core.exceptions import SearchUnavailableError
from app.domain.library import SourceRecord
from app.modules.resolution.provider.search_backend import SearchBackend


class FallbackSearchProvider:
    def __init__(self, primary: SearchBackend, standby: SearchBackend) -> None:
        self._primary = primary
        self._standby = standby
        self.last_used: str = primary.name

    @property
    def name(self) -> str:
        return f"{self._primary.name}+{self._standby.name}"

    async def find_by_doi(self, doi: str) -> SourceRecord | None:
        try:
            record = await self._primary.find_by_doi(doi)
        except SearchUnavailableError:
            self.last_used = self._standby.name
            return await self._standby.find_by_doi(doi)

        self.last_used = self._primary.name
        return record

    async def search(self, query: str, limit: int = 5) -> list[SourceRecord]:
        try:
            records = await self._primary.search(query, limit=limit)
        except SearchUnavailableError:
            self.last_used = self._standby.name
            return await self._standby.search(query, limit=limit)

        if records:
            self.last_used = self._primary.name
            return records

        self.last_used = self._standby.name
        return await self._standby.search(query, limit=limit)
