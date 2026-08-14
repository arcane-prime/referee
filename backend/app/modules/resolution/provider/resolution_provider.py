import asyncio

from app.core.exceptions import NotExtractedError
from app.domain.library import RawReference, Reference, Resolution
from app.modules.resolution.provider.matcher_provider import MatcherProvider
from app.modules.resolution.provider.search_backend import AbstractBackend, SearchBackend

CANDIDATES_PER_REFERENCE = 5
CANDIDATES_KEPT_WHEN_AMBIGUOUS = 3


class ResolutionProvider:
    def __init__(
        self,
        search: SearchBackend,
        matcher: MatcherProvider,
        abstracts: AbstractBackend | None = None,
        concurrency: int = 5,
    ) -> None:
        self._search = search
        self._matcher = matcher
        self._abstracts = abstracts
        self._concurrency = max(1, concurrency)

    async def resolve_all(self, references: list[RawReference]) -> list[Reference]:
        if not references:
            raise NotExtractedError(
                "This paper has no extracted references. Run extraction first."
            )

        limiter = asyncio.Semaphore(self._concurrency)

        async def run(raw: RawReference) -> Reference:
            async with limiter:
                return await self.resolve_one(raw)

        return list(await asyncio.gather(*(run(raw) for raw in references)))

    async def resolve_one(self, raw: RawReference) -> Reference:
        reference = Reference.from_raw(raw)

        records = await self._find_records(raw)
        candidates = self._matcher.rank(raw, records)
        status, best, reason = self._matcher.decide(candidates)

        resolution = Resolution(status=status, reason=reason)

        if best is not None:
            resolution.score = best.score.total
            resolution.matched = best.record.csl
            resolution.external_ids = best.record.external_ids
            resolution.abstract = best.record.abstract
            resolution.source_api = best.record.source_api

        if status == "ambiguous":
            resolution.candidates = candidates[:CANDIDATES_KEPT_WHEN_AMBIGUOUS]

        if status == "resolved":
            resolution.abstract_source = self._search.name if resolution.abstract else None
            await self._backfill_abstract(resolution)

        reference.resolution = resolution
        return reference

    async def _find_records(self, raw: RawReference):
        doi = raw.parsed.DOI if raw.parsed else None
        if doi:
            record = await self._search.find_by_doi(doi)
            if record is not None:
                return [record]

        query = (raw.parsed.title if raw.parsed and raw.parsed.title else None) or raw.raw
        return await self._search.search(query, limit=CANDIDATES_PER_REFERENCE)

    async def _backfill_abstract(self, resolution: Resolution) -> None:
        if resolution.abstract or self._abstracts is None:
            return

        title = resolution.matched.title if resolution.matched else None
        abstract = await self._abstracts.find_abstract(
            doi=resolution.external_ids.doi,
            title=title,
        )
        if abstract:
            resolution.abstract = abstract
            resolution.abstract_source = self._abstracts.name
