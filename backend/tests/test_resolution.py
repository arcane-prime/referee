import pytest

from app.domain.csl import CSLDate, CSLItem, CSLName
from app.domain.library import ExternalIds, RawReference, SourceRecord
from app.modules.resolution.provider.matcher_provider import (
    AMBIGUOUS_THRESHOLD,
    RESOLVED_THRESHOLD,
    MatcherProvider,
    author_similarity,
    normalise_text,
    title_similarity,
    year_similarity,
)
from app.modules.resolution.provider.openalex_provider import (
    reconstruct_abstract,
    split_display_name,
    strip_doi,
    strip_openalex_id,
)


def reference(title=None, authors=(), year=None, raw="a printed reference string"):
    parsed = None
    if title or authors or year:
        parsed = CSLItem(
            id="ref_0",
            title=title,
            author=[CSLName(family=surname) for surname in authors],
            issued=CSLDate.from_year(year),
        )
    return RawReference(id="ref_0", raw=raw, parsed=parsed)


def record(title=None, authors=(), year=None, doi=None, abstract=None):
    return SourceRecord(
        csl=CSLItem(
            id=doi or "openalex_w1",
            title=title,
            author=[CSLName(family=surname) for surname in authors],
            issued=CSLDate.from_year(year),
            DOI=doi,
        ),
        external_ids=ExternalIds(doi=doi, openalex="W1"),
        abstract=abstract,
        source_api="openalex",
    )


@pytest.fixture
def matcher():
    return MatcherProvider()


class TestOpenAlexFieldShapes:
    def test_doi_url_is_reduced_to_a_bare_doi(self):
        assert strip_doi("https://doi.org/10.1162/NECO.1997.9.8.1735") == (
            "10.1162/neco.1997.9.8.1735"
        )

    def test_openalex_id_url_is_reduced_to_an_id(self):
        assert strip_openalex_id("https://openalex.org/W2064675550") == "W2064675550"

    def test_inverted_index_is_rebuilt_in_word_order(self):
        prose = (
            "We propose a novel architecture that relies entirely on attention "
            "mechanisms to draw global dependencies between the input and the output "
            "sequence, dispensing with recurrence and convolutions altogether in "
            "every layer of the model."
        )
        inverted: dict[str, list[int]] = {}
        for position, word in enumerate(prose.split()):
            inverted.setdefault(word, []).append(position)

        assert reconstruct_abstract(inverted) == prose

    def test_missing_abstract_index_yields_none(self):
        assert reconstruct_abstract(None) is None
        assert reconstruct_abstract({}) is None

    def test_display_name_splits_on_the_last_token(self):
        name = split_display_name("Sepp Hochreiter")

        assert name.given == "Sepp"
        assert name.family == "Hochreiter"

    def test_single_token_name_is_kept_literal(self):
        assert split_display_name("Plato").literal == "Plato"

    def test_comma_ordered_name_is_read_family_first(self):
        name = split_display_name("Li, Yihan")

        assert name.family == "Li"
        assert name.given == "Yihan"

    def test_comma_ordered_name_keeps_a_multi_part_given_name(self):
        name = split_display_name("Buitelaar, Paul Andreas")

        assert name.family == "Buitelaar"
        assert name.given == "Paul Andreas"


class TestSimilarity:
    def test_normalisation_strips_case_accents_and_punctuation(self):
        assert normalise_text("Jürgen's Long-Term Memory!") == "jurgen s long term memory"

    def test_normalisation_folds_the_german_sharp_s(self):
        assert normalise_text("Roßmann") == normalise_text("Rossmann")

    def test_identical_titles_score_one(self):
        assert title_similarity("Long short-term memory", "Long Short-Term Memory") == 1.0

    def test_unrelated_titles_score_low(self):
        assert title_similarity("Attention is all you need", "Sobolev spaces") < 0.3

    def test_author_overlap_is_measured_against_our_authors_not_theirs(self):
        ours = CSLItem(id="a", author=[CSLName(family="Vaswani")])
        theirs = CSLItem(
            id="b",
            author=[CSLName(family="Vaswani"), CSLName(family="Shazeer")],
        )

        assert author_similarity(ours, theirs) == 1.0

    def test_author_similarity_is_none_when_either_side_has_no_authors(self):
        assert author_similarity(CSLItem(id="a"), CSLItem(id="b")) is None

    def test_one_year_gap_is_treated_as_a_near_match(self):
        preprint = CSLItem(id="a", issued=CSLDate.from_year(2016))
        published = CSLItem(id="b", issued=CSLDate.from_year(2017))

        assert year_similarity(preprint, published) == 0.85

    def test_distant_years_score_zero(self):
        assert year_similarity(
            CSLItem(id="a", issued=CSLDate.from_year(1997)),
            CSLItem(id="b", issued=CSLDate.from_year(2020)),
        ) == 0.0


class TestScoring:
    def test_a_perfect_match_resolves(self, matcher):
        ranked = matcher.rank(
            reference("Long short-term memory", ["Hochreiter", "Schmidhuber"], 1997),
            [record("Long Short-Term Memory", ["Hochreiter", "Schmidhuber"], 1997)],
        )
        status, best, _ = matcher.decide(ranked)

        assert status == "resolved"
        assert best.score.total >= RESOLVED_THRESHOLD

    def test_preprint_year_gap_still_resolves(self, matcher):
        ranked = matcher.rank(
            reference("Layer normalization", ["Ba", "Kiros", "Hinton"], 2016),
            [record("Layer Normalization", ["Ba", "Kiros", "Hinton"], 2017)],
        )

        assert matcher.decide(ranked)[0] == "resolved"

    def test_matching_title_with_wrong_authors_and_year_does_not_resolve(self, matcher):
        ranked = matcher.rank(
            reference("Long short-term memory", ["Hochreiter"], 1997),
            [record("Long short-term memory", ["Graves"], 2012)],
        )
        status, _, _ = matcher.decide(ranked)

        assert status != "resolved"

    def test_missing_signals_are_skipped_not_scored_as_zero(self, matcher):
        with_authors = matcher.score(
            reference("Attention is all you need", ["Vaswani"], 2017),
            record("Attention is all you need", ["Vaswani"], 2017),
        )
        without_authors = matcher.score(
            reference("Attention is all you need", (), 2017),
            record("Attention is all you need", ["Vaswani"], 2017),
        )

        assert without_authors.authors is None
        assert without_authors.total == pytest.approx(with_authors.total, abs=0.001)

    def test_reference_with_no_parsed_title_is_scored_on_its_raw_string(self, matcher):
        raw = "Jimmy Lei Ba, Jamie Ryan Kiros, and Geoffrey E Hinton. Layer normalization. 2016."
        ranked = matcher.rank(
            RawReference(id="ref_0", raw=raw, parsed=None),
            [record("Layer normalization", ["Ba", "Kiros", "Hinton"], 2016)],
        )

        assert ranked[0].score.title > 0.3

    def test_partial_parse_with_no_title_still_falls_back_to_the_raw_string(
        self, matcher
    ):
        raw = "Jimmy Lei Ba, Jamie Ryan Kiros, and Geoffrey E Hinton. Layer normalization. 2016."
        partial = RawReference(
            id="ref_0",
            raw=raw,
            parsed=CSLItem(id="ref_0", title=None, author=[CSLName(family="Ba")]),
        )

        ranked = matcher.rank(
            partial, [record("Layer normalization", ["Ba", "Kiros", "Hinton"], 2016)]
        )

        assert ranked[0].score.title > 0.3


class TestDecision:
    def test_no_candidates_is_unresolved_with_a_reason(self, matcher):
        status, best, reason = matcher.decide([])

        assert (status, best) == ("unresolved", None)
        assert reason

    def test_two_different_works_sharing_a_title_are_ambiguous_not_a_coin_flip(
        self, matcher
    ):
        ranked = matcher.rank(
            reference("Long short-term memory", [], None),
            [
                record("Long short-term memory", ["Hochreiter"], 1997, doi="10.1162/a"),
                record("Long short-term memory", ["Graves"], 2012, doi="10.1007/b"),
            ],
        )
        status, best, reason = matcher.decide(ranked)

        assert status == "ambiguous"
        assert best is not None
        assert "close" in reason.lower()

    def test_weak_best_candidate_is_unresolved(self, matcher):
        ranked = matcher.rank(
            reference("Attention is all you need", ["Vaswani"], 2017),
            [record("Sobolev spaces", ["Adams"], 1975)],
        )
        status, best, _ = matcher.decide(ranked)

        assert status == "unresolved"
        assert best is None

    def test_mid_confidence_is_ambiguous_and_keeps_the_candidate(self, matcher):
        ranked = matcher.rank(
            reference("Neural machine translation", ["Bahdanau"], 2014),
            [record("Neural machine translation by jointly learning", ["Cho"], 2014)],
        )
        status, best, _ = matcher.decide(ranked)

        if AMBIGUOUS_THRESHOLD <= ranked[0].score.total < RESOLVED_THRESHOLD:
            assert status == "ambiguous"
            assert best is not None


class TestDuplicateCollapsing:
    def test_a_preprint_and_its_published_version_are_one_candidate(self, matcher):
        published = record(
            "Learning Phrase Representations using RNN Encoder-Decoder",
            ["Cho", "Bahdanau"], 2014, doi="10.3115/v1/d14-1179", abstract="An abstract.",
        )
        preprint = record(
            "Learning Phrase Representations using RNN Encoder-Decoder",
            ["Cho", "Bahdanau"], 2014, doi="10.48550/arxiv.1406.1078",
        )
        ranked = matcher.rank(
            reference("Learning phrase representations using rnn encoder-decoder",
                      ["Cho", "Bahdanau"], 2014),
            [published, preprint],
        )

        assert len(ranked) == 1
        assert matcher.decide(ranked)[0] == "resolved"

    def test_the_published_version_with_an_abstract_survives(self, matcher):
        published = record("Same Title Here", ["Cho"], 2014,
                           doi="10.3115/v1/d14-1179", abstract="An abstract.")
        preprint = record("Same Title Here", ["Cho"], 2014, doi="10.48550/arxiv.1406.1078")
        ranked = matcher.rank(reference("Same title here", ["Cho"], 2014), [preprint, published])

        assert ranked[0].record.external_ids.doi == "10.3115/v1/d14-1179"
        assert ranked[0].record.abstract == "An abstract."

    def test_genuinely_different_works_are_not_collapsed(self, matcher):
        hochreiter = record("Long short-term memory", ["Hochreiter"], 1997, doi="10.1162/a")
        graves = record("Long short-term memory", ["Graves"], 2012, doi="10.1007/b")
        ranked = matcher.rank(reference("Long short-term memory", [], None), [hochreiter, graves])

        assert len(ranked) == 2
        assert matcher.decide(ranked)[0] == "ambiguous"

    def test_records_sharing_a_doi_are_collapsed_whatever_the_title(self, matcher):
        a = record("Attention Is All You Need", ["Vaswani"], 2017, doi="10.5555/x")
        b = record("Attention is all you need (extended abstract)", ["Vaswani"], 2017, doi="10.5555/x")
        ranked = matcher.rank(reference("Attention is all you need", ["Vaswani"], 2017), [a, b])

        assert len(ranked) == 1


class TestAbstractQuality:
    def test_a_real_abstract_is_accepted(self):
        from app.modules.resolution.provider.openalex_provider import (
            looks_like_an_abstract,
        )

        real = (
            "We propose the Transformer, a model architecture relying entirely on an "
            "attention mechanism to draw global dependencies between input and output. "
            "Experiments on two machine translation tasks show these models to be "
            "superior in quality while being more parallelizable and requiring "
            "significantly less time to train."
        )
        assert looks_like_an_abstract(real)

    def test_a_citation_string_is_rejected_as_an_abstract(self):
        from app.modules.resolution.provider.openalex_provider import (
            looks_like_an_abstract,
        )

        citation = (
            "Kyunghyun Cho, Bart van Merrienboer, Caglar Gulcehre, Dzmitry Bahdanau, "
            "Fethi Bougares, Holger Schwenk, Yoshua Bengio. Proceedings of the 2014 "
            "Conference on Empirical Methods in Natural Language Processing. 2014."
        )
        assert not looks_like_an_abstract(citation)

    def test_a_too_short_abstract_is_rejected(self):
        from app.modules.resolution.provider.openalex_provider import (
            looks_like_an_abstract,
        )

        assert not looks_like_an_abstract("A short note about the method.")

    def test_a_citation_shaped_index_reconstructs_to_none(self):
        from app.modules.resolution.provider.openalex_provider import reconstruct_abstract

        words = ["Kyunghyun", "Cho", "and", "Yoshua", "Bengio", ".", "Proceedings", "of", "EMNLP", ".", "2014", "."]
        inverted = {}
        for position, word in enumerate(words):
            inverted.setdefault(word, []).append(position)

        assert reconstruct_abstract(inverted) is None
