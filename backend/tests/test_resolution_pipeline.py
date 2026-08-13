import asyncio
import json
from pathlib import Path

import pytest

from app.domain.csl import CSLDate, CSLItem, CSLName
from app.domain.library import RawReference, SourceRecord
from app.modules.resolution.provider.matcher_provider import MatcherProvider
from app.modules.resolution.provider.openalex_provider import OpenAlexProvider
from app.modules.resolution.provider.resolution_provider import ResolutionProvider

WORK_FIXTURE = Path(__file__).parent / "fixtures" / "openalex_work.json"


def lstm_reference() -> RawReference:
    return RawReference(
        id="ref_12",
        raw="Sepp Hochreiter and Jürgen Schmidhuber. Long short-term memory. "
        "Neural Computation, 9(8):1735-1780, 1997.",
        parsed=CSLItem(
            id="ref_12",
            title="Long short-term memory",
            author=[CSLName(family="Hochreiter"), CSLName(family="Schmidhuber")],
            issued=CSLDate.from_year(1997),
        ),
    )


class StubSearch:
    name = "openalex"

    def __init__(self, records: list[SourceRecord], doi_record: SourceRecord | None = None):
        self._records = records
        self._doi_record = doi_record
        self.doi_lookups: list[str] = []
        self.searches: list[str] = []

    async def find_by_doi(self, doi: str) -> SourceRecord | None:
        self.doi_lookups.append(doi)
        return self._doi_record

    async def search(self, query: str, limit: int) -> list[SourceRecord]:
        self.searches.append(query)
        return self._records


class StubAbstracts:
    name = "semantic_scholar"

    def __init__(self, abstract: str | None):
        self._abstract = abstract
        self.calls: list[tuple[str | None, str | None]] = []

    async def find_abstract(self, doi: str | None, title: str | None) -> str | None:
        self.calls.append((doi, title))
        return self._abstract


@pytest.fixture(scope="module")
def openalex_record() -> SourceRecord:
    payload = json.loads(WORK_FIXTURE.read_text(encoding="utf-8"))
    return OpenAlexProvider(base_url="https://example.invalid")._to_record(payload)


def resolve(reference, search, abstracts=None):
    provider = ResolutionProvider(
        search=search,
        matcher=MatcherProvider(),
        abstracts=abstracts,
        concurrency=2,
    )
    return asyncio.run(provider.resolve_all([reference]))[0]


class TestRecordMapping:
    def test_a_real_openalex_payload_maps_into_csl(self, openalex_record):
        csl = openalex_record.csl

        assert csl.title == "Long Short-Term Memory"
        assert csl.year == 1997
        assert csl.container_title == "Neural Computation"
        assert csl.volume == "9"
        assert csl.page == "1735-1780"
        assert csl.first_author_surname == "Hochreiter"

    def test_identifiers_are_reduced_from_urls(self, openalex_record):
        assert openalex_record.external_ids.doi == "10.1162/neco.1997.9.8.1735"
        assert openalex_record.external_ids.openalex == "W2064675550"

    def test_the_abstract_is_readable_prose_not_an_index(self, openalex_record):
        assert openalex_record.abstract.startswith("Learning to store information")


class TestPipeline:
    def test_a_good_match_resolves_and_carries_everything_forward(self, openalex_record):
        reference = resolve(lstm_reference(), StubSearch([openalex_record]))

        assert reference.is_resolved
        assert reference.doi == "10.1162/neco.1997.9.8.1735"
        assert reference.has_abstract
        assert reference.resolution.source_api == "openalex"

    def test_csl_prefers_the_matched_record_over_our_parse(self, openalex_record):
        reference = resolve(lstm_reference(), StubSearch([openalex_record]))

        assert reference.parsed.container_title is None
        assert reference.csl.container_title == "Neural Computation"

    def test_the_original_printed_string_is_never_lost(self, openalex_record):
        reference = resolve(lstm_reference(), StubSearch([openalex_record]))

        assert "Hochreiter" in reference.raw

    def test_nothing_found_is_reported_as_unresolved_with_a_reason(self):
        reference = resolve(lstm_reference(), StubSearch([]))

        assert reference.resolution.status == "unresolved"
        assert reference.resolution.matched is None
        assert reference.resolution.reason

    def test_a_doi_short_circuits_the_search(self, openalex_record):
        with_doi = lstm_reference()
        with_doi.parsed.DOI = "10.1162/neco.1997.9.8.1735"
        search = StubSearch([], doi_record=openalex_record)

        reference = resolve(with_doi, search)

        assert search.doi_lookups == ["10.1162/neco.1997.9.8.1735"]
        assert search.searches == []
        assert reference.is_resolved

    def test_a_reference_with_no_title_is_searched_by_its_raw_string(self, openalex_record):
        titleless = RawReference(
            id="ref_20",
            raw="Sepp Hochreiter and Jurgen Schmidhuber. Long short-term memory. 1997.",
            parsed=None,
        )
        search = StubSearch([openalex_record])

        resolve(titleless, search)

        assert search.searches and "Hochreiter" in search.searches[0]


class TestAbstractFallback:
    def test_semantic_scholar_fills_an_abstract_openalex_lacks(self, openalex_record):
        without_abstract = openalex_record.model_copy(update={"abstract": None})
        abstracts = StubAbstracts("A fallback abstract from Semantic Scholar.")

        reference = resolve(lstm_reference(), StubSearch([without_abstract]), abstracts)

        assert reference.resolution.abstract_source == "semantic_scholar"
        assert reference.has_abstract
        assert abstracts.calls

    def test_the_fallback_is_skipped_when_openalex_already_had_one(self, openalex_record):
        abstracts = StubAbstracts("should not be used")

        reference = resolve(lstm_reference(), StubSearch([openalex_record]), abstracts)

        assert abstracts.calls == []
        assert reference.resolution.abstract_source == "openalex"

    def test_no_abstract_anywhere_is_survivable(self, openalex_record):
        without_abstract = openalex_record.model_copy(update={"abstract": None})

        reference = resolve(lstm_reference(), StubSearch([without_abstract]), StubAbstracts(None))

        assert reference.is_resolved
        assert not reference.has_abstract


class TestAgentSafety:
    def test_a_reference_parsed_from_the_pdf_may_not_be_cited_by_the_agent(
        self, openalex_record
    ):
        reference = resolve(lstm_reference(), StubSearch([openalex_record]))

        assert reference.provenance == "parsed_from_pdf"
        assert reference.can_be_cited_by_the_agent is False

    def test_an_api_sourced_reference_with_ids_may_be_cited(self, openalex_record):
        reference = resolve(lstm_reference(), StubSearch([openalex_record]))
        discovered = reference.model_copy(update={"provenance": "fetched_from_api"})

        assert discovered.can_be_cited_by_the_agent is True


# Notes
#
# These run the real orchestrator, the real matcher and the real OpenAlex
# mapping, with only the HTTP call replaced by a stub. That is the payoff of
# SearchBackend being a protocol returning domain objects: the whole stage is
# exercised end to end with no network and no quota.
#
# It also means the suite is unaffected by OpenAlex's daily budget, which is a
# real constraint. One paper costs forty to eighty requests against a free
# thousand a day, so tests that hit the live API would exhaust it and then fail
# for reasons unrelated to the code.
#
# The record fixture is a faithful copy of a real OpenAlex response, including
# the three shapes that are easy to get wrong: the DOI and id arriving as URLs,
# and the abstract arriving as an inverted index rather than as text. Mapping
# is asserted through OpenAlexProvider._to_record rather than by hand, so the
# production translation is what gets tested.
#
# test_csl_prefers_the_matched_record_over_our_parse is the one that
# demonstrates why this stage exists at all. Our parse had no journal; the
# resolved record does. That is output quality being decoupled from parser
# quality, asserted rather than claimed.
#
# The TestAgentSafety pair guards the anti-hallucination rule structurally. A
# reference scraped from the user's PDF can be resolved, carry a DOI and an
# abstract, and still be ineligible for the agent to cite in stage 4, because
# provenance records where it came from rather than how good it looks.
