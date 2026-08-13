import asyncio
import re

import httpx

from app.core.exceptions import SearchUnavailableError
from app.core.http_cache import HttpCache, request_key
from app.domain.csl import CSLDate, CSLItem, CSLName, CSLType
from app.domain.library import ExternalIds, SourceRecord

WORKS_PATH = "/works"
DOI_PREFIX = "https://doi.org/"
OPENALEX_ID_PREFIX = "https://openalex.org/"

MAX_QUERY_CHARS = 350

RATE_LIMIT_BACKOFF_SECONDS = (5.0, 15.0, 30.0)
LONGEST_WORTHWHILE_WAIT_SECONDS = 60.0

FILTER_RESERVED_CHARS = re.compile(r"[,|:+()<>=!?*\"]")

MIN_ABSTRACT_CHARS = 180
TRAILING_YEAR = re.compile(r"\.\s*(?:19|20)\d{2}\.?\s*$")
CITATION_SHAPED_MAX_CHARS = 500

CSL_TYPE_BY_OPENALEX_TYPE: dict[str, CSLType] = {
    "article": "article-journal",
    "journal-article": "article-journal",
    "preprint": "manuscript",
    "book": "book",
    "book-chapter": "chapter",
    "dissertation": "thesis",
    "report": "report",
    "dataset": "dataset",
    "proceedings-article": "paper-conference",
}

SELECT_FIELDS = ",".join(
    [
        "id",
        "doi",
        "display_name",
        "publication_year",
        "type",
        "authorships",
        "primary_location",
        "biblio",
        "abstract_inverted_index",
    ]
)


def looks_like_an_abstract(text: str | None) -> bool:
    if not text:
        return False

    stripped = text.strip()
    if len(stripped) < MIN_ABSTRACT_CHARS:
        return False

    if TRAILING_YEAR.search(stripped) and len(stripped) < CITATION_SHAPED_MAX_CHARS:
        return False

    return True


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None

    positioned = sorted(
        (position, word)
        for word, positions in inverted_index.items()
        for position in positions
    )
    abstract = " ".join(word for _, word in positioned).strip()

    if not looks_like_an_abstract(abstract):
        return None
    return abstract


def filter_safe(value: str) -> str:
    return " ".join(FILTER_RESERVED_CHARS.sub(" ", value).split())


def strip_doi(value: str | None) -> str | None:
    if not value:
        return None
    doi = value.strip()
    if doi.lower().startswith(DOI_PREFIX):
        doi = doi[len(DOI_PREFIX) :]
    return doi.lower() or None


def strip_openalex_id(value: str | None) -> str | None:
    if not value:
        return None
    identifier = value.strip()
    if identifier.startswith(OPENALEX_ID_PREFIX):
        identifier = identifier[len(OPENALEX_ID_PREFIX) :]
    return identifier or None


def split_display_name(display_name: str) -> CSLName:
    cleaned = " ".join(display_name.split())
    if not cleaned:
        return CSLName(literal=display_name)

    parts = cleaned.rsplit(" ", 1)
    if len(parts) == 1:
        return CSLName(literal=cleaned)
    return CSLName(given=parts[0], family=parts[1])


class OpenAlexProvider:
    name = "openalex"

    def __init__(
        self,
        base_url: str,
        mailto: str | None = None,
        timeout_seconds: float = 20.0,
        max_attempts: int = 3,
        cache: HttpCache | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._mailto = mailto
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._cache = cache

    async def find_by_doi(self, doi: str) -> SourceRecord | None:
        normalised = strip_doi(doi)
        if not normalised:
            return None

        payload = await self._get(
            f"{WORKS_PATH}/doi:{normalised}",
            params={"select": SELECT_FIELDS},
            allow_missing=True,
        )
        if payload is None:
            return None
        return self._to_record(payload)

    async def search(self, query: str, limit: int = 5) -> list[SourceRecord]:
        cleaned = " ".join(query.split())[:MAX_QUERY_CHARS]
        if not cleaned:
            return []

        results: list[dict] = []
        title_query = filter_safe(cleaned)

        if title_query:
            payload = await self._get(
                WORKS_PATH,
                params={
                    "filter": f"title.search:{title_query}",
                    "per-page": str(max(1, limit)),
                    "select": SELECT_FIELDS,
                },
            )
            results = (payload or {}).get("results") or []

        if not results:
            payload = await self._get(
                WORKS_PATH,
                params={
                    "search": cleaned,
                    "per-page": str(max(1, limit)),
                    "select": SELECT_FIELDS,
                },
            )
            results = (payload or {}).get("results") or []

        return [self._to_record(item) for item in results]

    async def _get(
        self,
        path: str,
        params: dict[str, str],
        allow_missing: bool = False,
    ) -> dict | None:
        query = dict(params)
        if self._mailto:
            query["mailto"] = self._mailto

        url = f"{self._base_url}{path}"
        cache_key = request_key(url, query)

        if self._cache is not None:
            cached = self._cache.get(self.name, cache_key)
            if cached is not None:
                return cached.get("payload")

        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(
                        url,
                        params=query,
                        headers={"User-Agent": self._user_agent()},
                    )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    break
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            if response.status_code == 404 and allow_missing:
                self._remember(cache_key, None)
                return None

            if response.status_code in (429, 503):
                retry_after = self._retry_after_seconds(response)

                if retry_after is not None and retry_after > LONGEST_WORTHWHILE_WAIT_SECONDS:
                    raise SearchUnavailableError(
                        "OpenAlex has exhausted this client's daily quota. It resets in "
                        f"{retry_after / 3600:.1f} hours. Set OPENALEX_MAILTO, or wait."
                    )

                if attempt == self._max_attempts:
                    raise SearchUnavailableError(
                        "OpenAlex is rate limiting this client. Try again shortly."
                    )

                index = min(attempt - 1, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)
                await asyncio.sleep(retry_after or RATE_LIMIT_BACKOFF_SECONDS[index])
                continue

            if response.status_code >= 400:
                raise SearchUnavailableError(
                    f"OpenAlex rejected the request with status {response.status_code}."
                )

            try:
                payload = response.json()
            except ValueError as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    break
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            self._remember(cache_key, payload)
            return payload

        raise SearchUnavailableError(f"Could not reach OpenAlex: {last_error}")

    def _remember(self, cache_key: str, payload: dict | None) -> None:
        if self._cache is not None:
            self._cache.put(self.name, cache_key, payload)

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        header = response.headers.get("retry-after")
        if not header:
            return None
        try:
            return float(header)
        except ValueError:
            return None

    def _user_agent(self) -> str:
        if self._mailto:
            return f"Referee/0.1 (mailto:{self._mailto})"
        return "Referee/0.1"

    def _to_record(self, work: dict) -> SourceRecord:
        doi = strip_doi(work.get("doi"))
        openalex_id = strip_openalex_id(work.get("id"))

        return SourceRecord(
            csl=CSLItem(
                id=openalex_id or doi or "openalex_unknown",
                type=CSL_TYPE_BY_OPENALEX_TYPE.get(
                    (work.get("type") or "").lower(), "article-journal"
                ),
                title=work.get("display_name") or None,
                author=self._authors(work),
                container_title=self._venue(work),
                issued=CSLDate.from_year(work.get("publication_year")),
                volume=self._biblio(work, "volume"),
                issue=self._biblio(work, "issue"),
                page=self._pages(work),
                DOI=doi,
                URL=f"{DOI_PREFIX}{doi}" if doi else None,
            ),
            external_ids=ExternalIds(doi=doi, openalex=openalex_id),
            abstract=reconstruct_abstract(work.get("abstract_inverted_index")),
            source_api=self.name,
        )

    def _authors(self, work: dict) -> list[CSLName]:
        names: list[CSLName] = []
        for authorship in work.get("authorships") or []:
            author = authorship.get("author") or {}
            display_name = author.get("display_name") or authorship.get("raw_author_name")
            if display_name:
                names.append(split_display_name(display_name))
        return names

    def _venue(self, work: dict) -> str | None:
        location = work.get("primary_location") or {}
        source = location.get("source") or {}
        return source.get("display_name") or None

    def _biblio(self, work: dict, key: str) -> str | None:
        biblio = work.get("biblio") or {}
        value = biblio.get(key)
        return str(value) if value else None

    def _pages(self, work: dict) -> str | None:
        biblio = work.get("biblio") or {}
        first = biblio.get("first_page")
        last = biblio.get("last_page")
        if first and last:
            return f"{first}-{last}"
        return str(first or last) if (first or last) else None


# Notes
#
# OpenAlex is the primary source because it needs no API key, which means a
# fresh clone of this repo resolves references without anyone signing up for
# anything. Sending a mailto opts into their polite pool, which is faster and
# more reliable, so the User-Agent and the query parameter both carry it.
#
# Three shapes in their responses need translating, and each one is a trap:
#
#   doi comes back as a URL ("https://doi.org/10.1162/...") rather than a bare
#   DOI. Comparing an unstripped value against a DOI parsed out of a PDF never
#   matches.
#
#   id is also a URL ("https://openalex.org/W2064675550").
#
#   abstract_inverted_index is a map of word to positions, not text. OpenAlex
#   publishes it this way for licensing reasons. reconstruct_abstract puts the
#   words back in order, which is the only way stage 3 ever sees an abstract.
#
# Some records carry a citation string in that field rather than an abstract.
# The RNN encoder-decoder paper reconstructs to "Kyunghyun Cho, Bart van
# Merrienboer, ... Proceedings of EMNLP. 2014." — perfectly ordered, and
# useless. It is a data quality problem at the source, not a reconstruction
# bug, and it is invisible unless you read the output.
#
# It matters because stage 3 checks claims against abstracts. Handing that
# string to the review model wastes a call and produces a finding that says
# nothing, so an abstract that does not look like prose is treated as absent.
# Semantic Scholar is then asked for it through the existing backfill, which
# is exactly the gap that fallback was built for.
#
# The test is deliberately blunt: too short to be an abstract, or short and
# ending in a bare year the way a citation does. Anything cleverer would risk
# discarding real abstracts, and a false negative here merely triggers a
# fallback lookup rather than losing information.
#
# Author names arrive as one display string, so split_display_name takes the
# last whitespace-separated token as the family name. That is a heuristic and
# it is wrong for names like "van Beethoven". It is acceptable here because
# matching compares surnames on both sides symmetrically and because the
# authoritative rendering at export time comes from the matched record's own
# fields, not from our split. It is called out rather than hidden.
#
# search falls back from a title filter to a general search when the title
# filter finds nothing. The title filter is precise and is what a real
# reference usually needs; the general search catches entries whose title we
# parsed badly, which is exactly the population most in need of a second
# chance.
#
# The select parameter asks for only the fields used here. OpenAlex records are
# large, and the abstract index in particular is heavy, so fetching whole works
# for forty references wastes bandwidth on both sides.
#
# A 404 on a DOI lookup is a legitimate answer meaning "no such work", not a
# failure, which is why it is allowed to return None rather than raise.
#
# filter_safe exists because OpenAlex's filter parameter has its own grammar,
# and ordinary title punctuation collides with it. Commas separate filters,
# colons split a key from its value, pipes mean OR, and — the one that is easy
# to miss — ? and * are wildcards, which the stemmed title.search field rejects
# outright with a 400.
#
# None of these are exotic. A title ending in a question mark ("Can active
# memory replace attention?") or containing a subtitle after a colon is
# completely normal, and every one of them fails the request rather than simply
# returning nothing. The characters are replaced with spaces rather than
# deleted so words either side do not weld together.
#
# The general search parameter has no such grammar, so the fallback path passes
# the query through untouched.
#
# OpenAlex enforces a daily budget as well as a rate, and the two are not the
# same failure. A burst is worth waiting a few seconds for; an exhausted daily
# quota comes back with a Retry-After measured in hours, and sleeping through
# that is pointless. Retry-After is therefore read rather than assumed, and a
# wait longer than a minute fails immediately with the real number in the
# message, so the caller learns "the quota resets in 9.7 hours" instead of
# watching a spinner and then reading "try again shortly".
#
# One paper is roughly forty to eighty requests against a free allowance of a
# thousand a day, so a dozen debugging runs exhausts it. That is the concrete
# argument for the deferred HTTP cache: without it, iterating on the matcher
# costs quota every time even though the answers never change.
