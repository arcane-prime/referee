from app.core.exceptions import SearchUnavailableError
from app.domain.library import Reference, SourceRecord
from app.domain.review import Sentence, SuggestedSource
from app.modules.resolution.provider.search_backend import SearchBackend
from app.modules.review.provider.llm_backend import LlmBackend

SCHEMA_NAME = "missing_work"

SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "relevant": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["index", "relevant", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}

SYSTEM = """You judge whether candidate papers would support a specific claim.

You are given a CLAIM from a paper, and numbered CANDIDATE papers found by a
literature search. For each candidate, decide whether citing it would actually
support this claim.

Answer true only when the candidate is genuinely about the same subject and
would be an appropriate citation for this exact claim.

Answer false when the candidate merely shares vocabulary, is about a different
problem, or is only loosely related. Search engines return topically similar
work constantly; most of it is not the right citation.

Be strict. A wrong suggestion wastes the author's time and damages trust in
every other suggestion.

Refer to candidates only by the index given. Give a one sentence reason."""

CANDIDATES_PER_CLAIM = 5
MAX_ABSTRACT_CHARS = 700
MAX_CLAIMS_INVESTIGATED = 12


class DiscoveryProvider:
    def __init__(self, llm: LlmBackend, search: SearchBackend) -> None:
        self._llm = llm
        self._search = search

    async def find_missing_work(
        self,
        sentence: Sentence,
        already_cited: set[str],
    ) -> list[SuggestedSource]:
        try:
            records = await self._search.search(
                sentence.text, limit=CANDIDATES_PER_CLAIM
            )
        except SearchUnavailableError:
            return []

        fresh = [
            record
            for record in records
            if self._identifier(record) and self._identifier(record) not in already_cited
        ]
        if not fresh:
            return []

        return await self._judge(sentence, fresh)

    async def _judge(
        self,
        sentence: Sentence,
        records: list[SourceRecord],
    ) -> list[SuggestedSource]:
        listing = "\n\n".join(
            f"[{index}] {record.csl.title or 'Untitled'}"
            f" ({record.csl.year or 'year unknown'})\n"
            f"{(record.abstract or 'No abstract available.')[:MAX_ABSTRACT_CHARS]}"
            for index, record in enumerate(records)
        )

        payload = await self._llm.complete_json(
            system=SYSTEM,
            user=f"CLAIM:\n{sentence.text}\n\nCANDIDATES:\n\n{listing}",
            schema=SCHEMA,
            schema_name=SCHEMA_NAME,
            max_tokens=1200,
        )

        suggestions: list[SuggestedSource] = []
        for entry in payload.get("suggestions") or []:
            index = entry.get("index")
            if not isinstance(index, int) or not (0 <= index < len(records)):
                continue
            if entry.get("relevant") is not True:
                continue

            record = records[index]
            suggestion = SuggestedSource(
                title=record.csl.title or "Untitled",
                doi=record.external_ids.doi,
                openalex_id=record.external_ids.openalex,
                url=f"https://doi.org/{record.external_ids.doi}"
                if record.external_ids.doi
                else None,
                year=record.csl.year,
                abstract=record.abstract,
                reason=(entry.get("reason") or "").strip() or None,
            )

            if suggestion.is_linkable:
                suggestions.append(suggestion)

        return suggestions

    @staticmethod
    def _identifier(record: SourceRecord) -> str | None:
        ids = record.external_ids
        return (ids.doi or ids.openalex or "").lower() or None

    @staticmethod
    def already_cited_identifiers(references: list[Reference]) -> set[str]:
        identifiers: set[str] = set()
        for reference in references:
            ids = reference.resolution.external_ids
            if ids.doi:
                identifiers.add(ids.doi.lower())
            if ids.openalex:
                identifiers.add(ids.openalex.lower())
        return identifiers


# Notes
#
# Pass B. Every suggestion here originates from a real search result, never
# from the model. The model is only allowed to select from candidates by index
# and say why, so it cannot propose a paper that does not exist. That is the
# same structural rule as the other passes, and it is the brief's hardest
# requirement: a review must never invent a citation.
#
# is_linkable is then enforced before a suggestion survives. A candidate with
# no DOI and no OpenAlex id is discarded even if the model liked it, because a
# suggestion a researcher cannot open is not actionable and is indistinguishable
# from a fabrication.
#
# Deduplication runs before the model is asked anything. Suggesting a paper the
# author already cites is the fastest way to look useless, and identifiers make
# that check exact where title matching would not be. It also saves tokens on
# candidates that were never going to be reportable.
#
# The prompt insists on strictness for the same reason the claim pass insists
# on conservatism. A literature search returns topically adjacent work by
# design, and a reviewer that suggests five loosely related papers per claim
# teaches the author to ignore the whole panel.
#
# Abstracts are truncated in the prompt because judging relevance needs the
# gist, not the full text, and five untruncated abstracts per claim across a
# dozen claims is a great deal of tokens for no extra accuracy.
#
# A search failure returns no suggestions rather than raising. Missing work is
# the enhancement half of review; the support checks are the half grounded in
# the paper's own bibliography, and an exhausted search quota should cost the
# first without taking down the second.
