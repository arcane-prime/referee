from lxml import etree

from app.core.exceptions import ExtractionFailedError
from app.domain.document import (
    FLOATS_SECTION_ID,
    FRONT_MATTER_SECTION_ID,
    Block,
    Document,
    Section,
)
from app.domain.geometry import BBox
from app.domain.library import RawReference
from app.modules.extraction.provider.id_minter import IdMinter
from app.modules.extraction.provider.inline_provider import InlineProvider
from app.modules.extraction.provider.reference_provider import ReferenceProvider
from app.modules.extraction.provider.tei_namespace import (
    find,
    find_all,
    local_name,
    normalise_space,
    text_of,
)

UNTITLED_SECTION = "Untitled section"
UNTITLED_PAPER = "Untitled paper"


class TeiProvider:
    def __init__(self, reference_provider: ReferenceProvider) -> None:
        self._references = reference_provider

    def parse(
        self,
        tei_xml: str,
        paper_id: str,
        document_id: str,
    ) -> tuple[Document, list[RawReference]]:
        root = self._root(tei_xml)
        minter = IdMinter()
        inlines = InlineProvider(minter)

        sections: list[Section] = []

        front_matter = self._front_matter(root, inlines)
        if front_matter is not None:
            sections.append(front_matter)

        sections.extend(self._body_sections(root, inlines))

        floats = self._floats(root, inlines)
        if floats is not None:
            sections.append(floats)

        document = Document(
            id=document_id,
            paper_id=paper_id,
            revision=0,
            title=self._title(root),
            authors=self._authors(root),
            sections=sections,
            seq=minter.seq,
        )

        return document, self._references.build_all(root)

    def _root(self, tei_xml: str) -> etree._Element:
        if not tei_xml.strip():
            raise ExtractionFailedError("The parser returned an empty document.")

        parser = etree.XMLParser(recover=True, huge_tree=True)
        try:
            root = etree.fromstring(tei_xml.encode("utf-8"), parser=parser)
        except etree.XMLSyntaxError as exc:
            raise ExtractionFailedError(f"The parser returned invalid XML: {exc}") from exc

        if root is None:
            raise ExtractionFailedError("The parser returned invalid XML.")
        return root

    def _title(self, root: etree._Element) -> str:
        node = find(root, ".//tei:teiHeader//tei:titleStmt/tei:title[@type='main']")
        if node is None:
            node = find(root, ".//tei:teiHeader//tei:titleStmt/tei:title")

        title = text_of(node)
        if title:
            return title

        first_head = find(root, ".//tei:text/tei:body//tei:head")
        return text_of(first_head) or UNTITLED_PAPER

    def _authors(self, root: etree._Element) -> list[str]:
        persons = find_all(
            root,
            ".//tei:teiHeader//tei:sourceDesc//tei:analytic/tei:author/tei:persName",
        )

        authors: list[str] = []
        for person in persons:
            forenames = [text_of(node) for node in find_all(person, "./tei:forename")]
            surname = text_of(find(person, "./tei:surname"))
            full = normalise_space(" ".join([*forenames, surname]))
            if full and full not in authors:
                authors.append(full)
        return authors

    def _front_matter(
        self,
        root: etree._Element,
        inlines: InlineProvider,
    ) -> Section | None:
        abstract = find(root, ".//tei:teiHeader//tei:profileDesc/tei:abstract")
        if abstract is None:
            return None

        paragraphs = find_all(abstract, ".//tei:p")
        sources = paragraphs or [abstract]

        blocks: list[Block] = []
        for index, paragraph in enumerate(sources):
            nodes = inlines.build(paragraph)
            if not nodes:
                continue
            blocks.append(
                Block(
                    id=f"{FRONT_MATTER_SECTION_ID}.p{index}",
                    kind="abstract",
                    inlines=nodes,
                    coords=BBox.parse_coords(paragraph.get("coords")),
                )
            )

        if not blocks:
            return None

        return Section(
            id=FRONT_MATTER_SECTION_ID,
            title="Abstract",
            level=1,
            blocks=blocks,
        )

    def _body_sections(
        self,
        root: etree._Element,
        inlines: InlineProvider,
    ) -> list[Section]:
        body = find(root, ".//tei:text/tei:body")
        if body is None:
            return []

        sections: list[Section] = []
        for div in find_all(body, ".//tei:div"):
            section = self._section(div, len(sections), inlines)
            if section is not None:
                sections.append(section)
        return sections

    def _section(
        self,
        div: etree._Element,
        index: int,
        inlines: InlineProvider,
    ) -> Section | None:
        section_id = f"s{index}"
        head = find(div, "./tei:head")

        blocks: list[Block] = []
        for child in div:
            block = self._block(child, section_id, len(blocks), inlines)
            if block is not None:
                blocks.append(block)

        if not blocks:
            return None

        return Section(
            id=section_id,
            title=text_of(head) or UNTITLED_SECTION,
            level=self._level(head),
            blocks=blocks,
        )

    def _block(
        self,
        element: etree._Element,
        section_id: str,
        index: int,
        inlines: InlineProvider,
    ) -> Block | None:
        name = local_name(element)
        if name not in ("p", "formula"):
            return None

        nodes = inlines.build_element(element) if name == "formula" else inlines.build(element)
        if not nodes:
            return None

        return Block(
            id=f"{section_id}.p{index}",
            kind="paragraph" if name == "p" else "formula",
            inlines=nodes,
            coords=BBox.parse_coords(element.get("coords")),
        )

    def _level(self, head: etree._Element | None) -> int:
        if head is None:
            return 1
        numbering = (head.get("n") or "").strip().rstrip(".")
        if not numbering:
            return 1
        return numbering.count(".") + 1

    def _floats(
        self,
        root: etree._Element,
        inlines: InlineProvider,
    ) -> Section | None:
        figures = find_all(root, ".//tei:text/tei:body//tei:figure")
        if not figures:
            return None

        blocks: list[Block] = []
        for figure in figures:
            description = find(figure, "./tei:figDesc")
            if description is None:
                continue

            nodes = inlines.build(description)
            if not nodes:
                continue

            blocks.append(
                Block(
                    id=f"{FLOATS_SECTION_ID}.p{len(blocks)}",
                    kind="caption",
                    inlines=nodes,
                    label=text_of(find(figure, "./tei:head")) or None,
                    coords=BBox.parse_coords(figure.get("coords")),
                )
            )

        if not blocks:
            return None

        return Section(
            id=FLOATS_SECTION_ID,
            title="Figures and tables",
            level=1,
            blocks=blocks,
        )


# Notes
#
# This is the translator: TEI in, domain models out. It performs no I/O and
# takes a string, which is what lets the whole parser be tested against a
# committed fixture with no container and no network.
#
# Every block lives inside a section, so the abstract and the figure captions
# get synthetic sections rather than becoming fields hanging off Document. That
# keeps traversal uniform: anything that walks the paper sees one shape and has
# no special cases, and the citation count is automatically correct because
# captions are in the same walk as body paragraphs.
#
# Captions are included and footnotes are not. Captions routinely cite work,
# and leaving them out would make the citation-preservation count quietly wrong
# for any paper that cites inside a figure caption. Footnotes being excluded is
# a stated limitation rather than an oversight.
#
# Section level comes from the numbering GROBID puts on <head n="3.1">, so
# subsections are represented by depth rather than by nesting. Sections are a
# flat list because nothing downstream walks a tree.
#
# The recover=True parser is deliberate. Real GROBID output occasionally
# contains a malformed span, and salvaging the rest of a large document is
# better than rejecting the paper outright. A document that cannot be salvaged
# at all still raises.
#
# Title falls back to the first heading in the body when the header has none,
# and only then to a placeholder, so the failure is visible rather than
# crashing the parse.
#
# A display formula is a block-level sibling of <p> inside a div, not something
# nested in a paragraph. It is therefore built with build_element, which treats
# the element itself as one node, rather than with build, which walks it as a
# container. Walking it as a container flattens the equation into a TextRun,
# which would hand the equation to the LLM as editable prose and defeat the
# reason MathNode exists.
#
# Blocks whose inline walk produced nothing are skipped, and a section whose
# blocks are all empty is skipped with them. That drops the layout artefacts
# GROBID emits for page furniture without discarding anything a reader would
# recognise as content.
