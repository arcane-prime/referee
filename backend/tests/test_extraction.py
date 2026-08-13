import re
from pathlib import Path

import pytest
from lxml import etree

from app.domain.document import CiteNode, MathNode, TextRun, XRefNode
from app.modules.extraction.provider.id_minter import IdMinter
from app.modules.extraction.provider.inline_provider import InlineProvider
from app.modules.extraction.provider.reference_provider import ReferenceProvider
from app.modules.extraction.provider.style_provider import StyleProvider
from app.modules.extraction.provider.tei_provider import TeiProvider

FIXTURE = Path(__file__).parent / "fixtures" / "numbered.tei.xml"
TEI_NS = 'xmlns="http://www.tei-c.org/ns/1.0"'

NUMBERED_MARKER = re.compile(r"[\[\]]")
AUTHOR_YEAR_MARKER = re.compile(r"\(\s*[A-Z][A-Za-z'`-]+[^()]{0,40}\b(1[6-9]\d{2}|20\d{2})\s*\)")


def build_inlines(paragraph_xml: str):
    element = etree.fromstring(f"<p {TEI_NS}>{paragraph_xml}</p>".encode("utf-8"))
    return InlineProvider(IdMinter()).build(element)


def parse_tei(tei_xml: str):
    return TeiProvider(ReferenceProvider()).parse(
        tei_xml=tei_xml, paper_id="paper_test", document_id="paper_test_rev0"
    )


def only_citation(nodes) -> CiteNode:
    citations = [node for node in nodes if isinstance(node, CiteNode)]
    assert len(citations) == 1
    return citations[0]


def prose_of(nodes) -> str:
    return "".join(node.text for node in nodes if isinstance(node, TextRun))


@pytest.fixture(scope="module")
def parsed():
    return parse_tei(FIXTURE.read_text(encoding="utf-8"))


class TestInlineWalk:
    @pytest.mark.parametrize(
        "paragraph",
        [
            'networks <ref type="bibr" target="#b12">[12]</ref> are strong.',
            'networks [<ref type="bibr" target="#b12">12</ref>] are strong.',
        ],
        ids=["delimiters-inside-ref", "delimiters-outside-ref"],
    )
    def test_both_delimiter_placements_produce_the_same_node(self, paragraph):
        nodes = build_inlines(paragraph)
        citation = only_citation(nodes)

        assert citation.ref_ids == ["ref_12"]
        assert citation.raw_marker == "[12]"
        assert not NUMBERED_MARKER.search(prose_of(nodes))

    def test_author_year_parentheses_are_absorbed(self):
        nodes = build_inlines(
            'shown by (<ref type="bibr" target="#b7">Smith et al., 2019</ref>) it holds.'
        )
        citation = only_citation(nodes)

        assert citation.raw_marker == "(Smith et al., 2019)"
        assert not AUTHOR_YEAR_MARKER.search(prose_of(nodes))

    @pytest.mark.parametrize(
        "paragraph",
        [
            'work [<ref type="bibr" target="#b12">12</ref>, '
            '<ref type="bibr" target="#b13">13</ref>] shows.',
            'work [<ref type="bibr" target="#b12">12</ref>], '
            '[<ref type="bibr" target="#b13">13</ref>] shows.',
            'work [<ref type="bibr" target="#b12">12</ref>,'
            '<ref type="bibr" target="#b13">13</ref>] shows.',
        ],
        ids=["shared-brackets", "separate-brackets", "no-space-separator"],
    )
    def test_grouped_markers_merge_into_one_citation_act(self, paragraph):
        nodes = build_inlines(paragraph)
        citation = only_citation(nodes)

        assert citation.ref_ids == ["ref_12", "ref_13"]

    def test_ranges_keep_endpoints_and_never_invent_references(self):
        nodes = build_inlines(
            'see [<ref type="bibr" target="#b12">12</ref>]-'
            '[<ref type="bibr" target="#b15">15</ref>] for detail.'
        )
        citation = only_citation(nodes)

        assert citation.ref_ids == ["ref_12", "ref_15"]
        assert "ref_13" not in citation.ref_ids
        assert "ref_14" not in citation.ref_ids
        assert citation.raw_marker == "[12]-[15]"

    def test_marker_without_target_is_kept_as_unlinked(self):
        nodes = build_inlines('claim [<ref type="bibr">99</ref>] unlinked.')
        citation = only_citation(nodes)

        assert citation.ref_ids == []
        assert citation.is_linked is False
        assert citation.raw_marker == "[99]"

    def test_figure_reference_and_formula_become_their_own_nodes(self):
        nodes = build_inlines(
            'as in <ref type="figure" target="#fig_0">Figure 1</ref> the cost is '
            "<formula>O(n^2)</formula> here."
        )

        xrefs = [node for node in nodes if isinstance(node, XRefNode)]
        maths = [node for node in nodes if isinstance(node, MathNode)]

        assert [node.label for node in xrefs] == ["Figure 1"]
        assert xrefs[0].target_kind == "figure"
        assert [node.source for node in maths] == ["O(n^2)"]

    def test_footnote_markers_are_dropped_not_flattened(self):
        nodes = build_inlines('a sentence<ref type="foot" target="#foot_0">1</ref> continues.')

        assert prose_of(nodes) == "a sentence continues."

    def test_formatting_wrappers_keep_their_text(self):
        nodes = build_inlines('text with <hi rend="italic">emphasis</hi> inside.')

        assert prose_of(nodes) == "text with emphasis inside."


class TestNoMarkersInProse:
    def test_no_numbered_marker_survives_into_editable_prose(self, parsed):
        document, _ = parsed

        leaks = [
            (block.id, node.text)
            for block in document.blocks()
            for node in block.inlines
            if isinstance(node, TextRun) and NUMBERED_MARKER.search(node.text)
        ]

        assert leaks == []

    def test_no_author_year_marker_survives_into_editable_prose(self, parsed):
        document, _ = parsed

        leaks = [
            (block.id, node.text)
            for block in document.blocks()
            for node in block.inlines
            if isinstance(node, TextRun) and AUTHOR_YEAR_MARKER.search(node.text)
        ]

        assert leaks == []

    def test_ordinary_parentheses_in_prose_are_left_alone(self, parsed):
        document, _ = parsed
        prose = " ".join(block.display_text for block in document.blocks())

        assert "(" in prose


class TestDocumentStructure:
    def test_paper_title_is_extracted(self, parsed):
        document, _ = parsed

        assert "Attention Is All You Need" in document.title

    def test_paper_authors_are_extracted(self, parsed):
        document, _ = parsed

        for expected in ("Ashish Vaswani", "Noam Shazeer", "Niki Parmar"):
            assert expected in document.authors

    def test_abstract_lives_in_the_front_matter_section(self, parsed):
        document, _ = parsed
        front = document.sections[0]

        assert front.id == "s_front"
        assert front.blocks[0].kind == "abstract"
        assert "attention" in front.blocks[0].display_text.lower()

    def test_subsection_depth_comes_from_head_numbering(self, parsed):
        document, _ = parsed
        levels = {section.title: section.level for section in document.sections}

        assert levels["Introduction"] == 1
        assert levels["Encoder and Decoder Stacks"] == 2
        assert levels["Scaled Dot-Product Attention"] == 3

    def test_block_ids_are_unique_and_section_scoped(self, parsed):
        document, _ = parsed
        ids = [block.id for block in document.blocks()]

        assert "s0.p0" in ids
        assert len(ids) == len(set(ids))

    def test_display_formulas_are_math_nodes_not_prose(self, parsed):
        document, _ = parsed
        formula_blocks = [block for block in document.blocks() if block.kind == "formula"]

        assert formula_blocks
        for block in formula_blocks:
            assert all(isinstance(node, MathNode) for node in block.inlines)
            assert block.display_text == ""

    def test_captions_are_captured_as_their_own_blocks(self, parsed):
        document, _ = parsed
        floats = [section for section in document.sections if section.id == "s_floats"]

        assert floats
        assert all(block.kind == "caption" for block in floats[0].blocks)

    def test_a_citation_inside_a_caption_is_counted(self):
        tei = f"""<TEI {TEI_NS}><text><body>
            <figure xml:id="fig_0"><head>Figure 1</head>
              <figDesc>Architecture following <ref type="bibr" target="#b4">[5]</ref>.</figDesc>
            </figure>
        </body></text></TEI>"""

        document, _ = parse_tei(tei)

        assert document.ref_id_counts() == {"ref_4": 1}

    def test_coordinates_are_captured_for_citations(self, parsed):
        document, _ = parsed
        citations = document.cite_nodes()

        assert citations
        assert all(node.coords for node in citations)
        assert citations[0].coords[0].page >= 1


class TestReferences:
    def test_all_references_are_extracted(self, parsed):
        _, references = parsed

        assert len(references) == 40

    def test_every_reference_keeps_its_verbatim_string(self, parsed):
        _, references = parsed

        assert all(reference.raw.strip() for reference in references)

    def test_reference_without_a_title_is_kept_not_dropped(self, parsed):
        _, references = parsed
        failed = [ref for ref in references if ref.parse_quality == "failed"]

        assert failed
        for reference in failed:
            assert reference.raw.strip()
            assert "title" in reference.missing_fields

    def test_fields_are_mapped_into_csl(self, parsed):
        _, references = parsed
        lstm = next(ref for ref in references if ref.id == "ref_12")

        assert lstm.parsed is not None
        assert lstm.parsed.title == "Long short-term memory"
        assert lstm.parsed.year == 1997
        assert lstm.parsed.first_author_surname == "Hochreiter"
        assert lstm.parsed.page == "1735-1780"

    def test_quality_is_derived_from_the_fields_present(self, parsed):
        _, references = parsed
        by_id = {ref.id: ref for ref in references}

        assert by_id["ref_12"].parse_quality == "good"
        assert by_id["ref_0"].parse_quality == "failed"
        assert by_id["ref_29"].parse_quality == "degraded"
        assert by_id["ref_29"].missing_fields == ["authors"]

    def test_every_citation_resolves_to_a_known_reference(self, parsed):
        document, references = parsed
        known = {reference.id for reference in references}

        linked = {
            ref_id
            for node in document.cite_nodes()
            for ref_id in node.ref_ids
        }

        assert linked
        assert linked <= known


class TestStyleDetection:
    def test_numbered_markers_are_detected_as_ieee(self, parsed):
        document, _ = parsed
        style, confidence = StyleProvider().detect(document.cite_nodes())

        assert style == "ieee"
        assert confidence > 0.7

    def test_author_year_markers_are_detected_as_apa(self):
        nodes = [
            CiteNode(id=f"c_{index}", raw_marker=marker)
            for index, marker in enumerate(
                ["(Smith et al., 2019)", "(Jones, 2020)", "(Lee and Park, 2018)"]
            )
        ]

        assert StyleProvider().detect(nodes)[0] == "apa"

    def test_too_few_markers_stays_unknown(self):
        nodes = [CiteNode(id="c_1", raw_marker="[1]")]

        assert StyleProvider().detect(nodes) == ("unknown", 0.0)


# Notes
#
# The fixture is real GROBID 0.8 output for arXiv 1706.03762, captured by
# running the container once and committing the TEI. The suite therefore runs
# against genuine parser output with no container and no network, which is the
# payoff of grobid_provider returning a plain string.
#
# TestNoMarkersInProse is the suite that matters most. Everything in stages 3
# and 4 assumes citations are nodes rather than characters, so if a marker ever
# survives into a TextRun the LLM can delete a citation by rewriting a sentence
# and the count-based invariant silently stops protecting anything.
#
# The two marker checks are deliberately different shapes. Square brackets do
# not otherwise occur in academic prose, so their presence is proof of a leak.
# Parentheses do occur constantly - "(x 1 , ..., x n )", "LayerNorm(x +
# Sublayer(x))", "(multiplicative)" - so an author-year leak has to be matched
# on the pattern of a name followed by a year, not on the bracket character. An
# earlier version of this suite flagged all four characters and reported 24
# failures against real prose, none of which were leaks.
#
# test_ordinary_parentheses_in_prose_are_left_alone guards the opposite
# mistake: a parser that stripped every parenthesis would pass both leak tests
# while destroying the text.
#
# The delimiter tests are parametrised over both placements because GROBID
# emits both, and a parser handling only one looks correct on whichever paper
# was tried first. The no-space case is included because real output contains
# "[35,2,5]" with no spaces after the commas.
#
# The range test asserts the absences. Expanding "[12]-[15]" into four ids
# would invent two references the markup never stated, which is the one failure
# this product cannot ship.
#
# test_a_citation_inside_a_caption_is_counted uses a minimal inline TEI rather
# than the fixture, because this particular paper happens to have no cited
# figure captions. The mechanism still needs a guard: if captions were dropped,
# any paper that cites inside one would silently report the wrong citation
# count, and the edit invariant would be comparing wrong numbers.
