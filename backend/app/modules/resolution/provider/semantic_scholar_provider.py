import asyncio

import httpx

from app.core.http_cache import HttpCache, request_key
from app.domain.csl import CSLDate, CSLItem, CSLType
from app.domain.library import ExternalIds, SourceRecord
from app.modules.resolution.provider.openalex_provider import split_display_name

SEARCH_PATH = "/graph/v1/paper/search"
PAPER_PATH = "/graph/v1/paper"

RECORD_FIELDS = "paperId,title,year,abstract,externalIds,authors,venue,publicationTypes"
ABSTRACT_FIELDS = "abstract,title,externalIds"

MAX_QUERY_CHARS = 250
RATE_LIMIT_BACKOFF_SECONDS = (3.0, 8.0, 20.0)

CSL_TYPE_BY_S2_TYPE: dict[str, CSLType] = {
    "JournalArticle": "article-journal",
    "Conference": "paper-conference",
    "Book": "book",
    "BookSection": "chapter",
    "Dataset": "dataset",
    "Review": "article-journal",
}


class SemanticScholarProvider:
    name = "semantic_scholar"

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 20.0,
        max_attempts: int = 4,
        cache: HttpCache | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._cache = cache

    async def find_by_doi(self, doi: str) -> SourceRecord | None:
        payload = await self._get(
            f"{PAPER_PATH}/DOI:{doi}", params={"fields": RECORD_FIELDS}
        )
        if not payload:
            return None
        return self._to_record(payload)

    async def search(self, query: str, limit: int = 5) -> list[SourceRecord]:
        cleaned = " ".join(query.split())[:MAX_QUERY_CHARS]
        if not cleaned:
            return []

        payload = await self._get(
            SEARCH_PATH,
            params={"query": cleaned, "fields": RECORD_FIELDS, "limit": str(max(1, limit))},
        )
        results = (payload or {}).get("data") or []
        return [self._to_record(item) for item in results if item]

    async def find_abstract(self, doi: str | None, title: str | None) -> str | None:
        if doi:
            payload = await self._get(
                f"{PAPER_PATH}/DOI:{doi}", params={"fields": ABSTRACT_FIELDS}
            )
            abstract = self._clean((payload or {}).get("abstract"))
            if abstract:
                return abstract

        if not title:
            return None

        cleaned = " ".join(title.split())[:MAX_QUERY_CHARS]
        payload = await self._get(
            SEARCH_PATH,
            params={"query": cleaned, "fields": ABSTRACT_FIELDS, "limit": "1"},
        )
        results = (payload or {}).get("data") or []
        if not results:
            return None
        return self._clean(results[0].get("abstract"))

    async def _get(self, path: str, params: dict[str, str]) -> dict | None:
        url = f"{self._base_url}{path}"
        cache_key = request_key(url, params)

        if self._cache is not None:
            cached = self._cache.get(self.name, cache_key)
            if cached is not None:
                return cached.get("payload")

        headers = {"User-Agent": "Referee/0.1"}
        if self._api_key:
            headers["x-api-key"] = self._api_key

        for attempt in range(1, self._max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(url, params=params, headers=headers)
            except httpx.HTTPError:
                if attempt == self._max_attempts:
                    return None
                await asyncio.sleep(2.0 * attempt)
                continue

            if response.status_code == 429:
                if attempt == self._max_attempts:
                    return None
                index = min(attempt - 1, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)
                await asyncio.sleep(RATE_LIMIT_BACKOFF_SECONDS[index])
                continue

            if response.status_code == 404:
                self._remember(cache_key, None)
                return None

            if response.status_code >= 400:
                return None

            try:
                payload = response.json()
            except ValueError:
                return None

            self._remember(cache_key, payload)
            return payload

        return None

    def _remember(self, cache_key: str, payload: dict | None) -> None:
        if self._cache is not None:
            self._cache.put(self.name, cache_key, payload)

    def _to_record(self, paper: dict) -> SourceRecord:
        external = paper.get("externalIds") or {}
        doi = (external.get("DOI") or "").lower() or None
        paper_id = paper.get("paperId") or None

        types = paper.get("publicationTypes") or []
        csl_type: CSLType = "article-journal"
        for entry in types:
            if entry in CSL_TYPE_BY_S2_TYPE:
                csl_type = CSL_TYPE_BY_S2_TYPE[entry]
                break

        return SourceRecord(
            csl=CSLItem(
                id=paper_id or doi or "s2_unknown",
                type=csl_type,
                title=paper.get("title") or None,
                author=[
                    split_display_name(author["name"])
                    for author in (paper.get("authors") or [])
                    if author.get("name")
                ],
                container_title=paper.get("venue") or None,
                issued=CSLDate.from_year(paper.get("year")),
                DOI=doi,
                URL=f"https://doi.org/{doi}" if doi else None,
            ),
            external_ids=ExternalIds(doi=doi, semantic_scholar=paper_id),
            abstract=self._clean(paper.get("abstract")),
            source_api=self.name,
        )

    @staticmethod
    def _clean(abstract: str | None) -> str | None:
        if not abstract:
            return None
        cleaned = " ".join(abstract.split())
        return cleaned or None
