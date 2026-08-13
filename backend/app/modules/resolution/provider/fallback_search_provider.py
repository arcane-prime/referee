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


# Notes
#
# One source answers at a time. This is a fallback chain, not a vote: the
# standby is consulted only when the primary either cannot answer at all or
# found nothing, and whichever record comes back is scored by the same matcher
# against the same thresholds. Merging results from two databases would mean
# two different notions of identity competing with no shared ranking.
#
# It falls through on two distinct conditions. SearchUnavailableError means the
# primary is down or out of quota, which is an availability problem. An empty
# result set means the primary is healthy but has no record, which happens for
# preprints and workshop papers that one index carries and the other does not.
# Both are worth a second opinion; neither is worth overriding a match the
# primary already made.
#
# OpenAlex's daily budget is what makes this more than theoretical. Once it is
# spent, every request for the rest of the day fails, and without a standby the
# whole stage would simply stop working until midnight UTC. Semantic Scholar
# fails on a short shared rate limit instead, so the two are unlikely to be
# unavailable for the same reason at the same time.
#
# last_used is recorded so the response can report which database actually
# answered. A researcher checking their bibliography deserves to know whether a
# match came from the primary index or a fallback.
