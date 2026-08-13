from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.domain.geometry import BBox

FRONT_MATTER_SECTION_ID = "s_front"
FLOATS_SECTION_ID = "s_floats"


class TextRun(BaseModel):
    kind: Literal["text"] = "text"
    text: str


class CiteNode(BaseModel):
    kind: Literal["cite"] = "cite"
    id: str
    ref_ids: list[str] = Field(default_factory=list)

    raw_marker: str | None = None
    prefix: str | None = None
    locator: str | None = None

    coords: list[BBox] = Field(default_factory=list)

    @property
    def is_linked(self) -> bool:
        return bool(self.ref_ids)


class XRefNode(BaseModel):
    kind: Literal["xref"] = "xref"
    id: str
    target_kind: Literal["figure", "table", "section", "equation", "unknown"] = "unknown"
    target_id: str | None = None
    label: str

    coords: list[BBox] = Field(default_factory=list)


class MathNode(BaseModel):
    kind: Literal["math"] = "math"
    id: str
    source: str
    coords: list[BBox] = Field(default_factory=list)


Inline = Annotated[TextRun | CiteNode | XRefNode | MathNode, Field(discriminator="kind")]

BlockKind = Literal["paragraph", "heading", "abstract", "caption", "formula"]


class Block(BaseModel):
    id: str
    kind: BlockKind = "paragraph"
    inlines: list[Inline] = Field(default_factory=list)
    label: str | None = None

    coords: list[BBox] = Field(default_factory=list)

    @property
    def cite_nodes(self) -> list[CiteNode]:
        return [node for node in self.inlines if isinstance(node, CiteNode)]

    @property
    def display_text(self) -> str:
        return "".join(node.text for node in self.inlines if isinstance(node, TextRun))


class Section(BaseModel):
    id: str
    title: str
    level: int = 1
    blocks: list[Block] = Field(default_factory=list)


CitationStyle = Literal["ieee", "apa", "nature", "unknown"]


class Document(BaseModel):
    id: str
    paper_id: str
    revision: int = 0

    title: str
    authors: list[str] = Field(default_factory=list)

    style: CitationStyle = "unknown"
    style_confidence: float = 0.0

    sections: list[Section] = Field(default_factory=list)
    seq: int = 0

    def blocks(self):
        for section in self.sections:
            yield from section.blocks

    def block(self, block_id: str) -> Block | None:
        return next((block for block in self.blocks() if block.id == block_id), None)

    def cite_nodes(self) -> list[CiteNode]:
        return [node for block in self.blocks() for node in block.cite_nodes]

    def ref_id_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self.cite_nodes():
            for ref_id in node.ref_ids:
                counts[ref_id] = counts.get(ref_id, 0) + 1
        return counts


# Notes
#
# A paragraph is not a string. It is a list of inline nodes, and the things
# that must survive an edit are nodes rather than characters inside prose.
# The rule this buys, and the reason the model is shaped this way:
#
#     The LLM writes TextRun content and nothing else. Every other inline is
#     selected, moved, or removed with the user's approval, never authored.
#
# Two consequences follow. An LLM rewriting prose cannot delete a citation,
# because the citation was never part of the prose it was handed. And citation
# preservation becomes countable, so "never break citations" is a check rather
# than a request. ref_id_counts() is that check: stage 4 compares two of these
# dicts across a proposed edit.
#
# The characters "[12, 15]" exist nowhere in stored data. They are produced at
# render time by citeproc, which is also how one document prints as IEEE or APA
# without the data changing.
#
# TextRun carries an invariant enforced by tests: no TextRun produced by
# extraction contains a citation marker. GROBID routinely emits delimiters
# outside the <ref> element, so the parser absorbs them into the CiteNode
# rather than leaving them stranded in editable prose.
#
# CiteNode.ref_ids may hold several ids because "[12, 13]" is a single citation
# act attached to a single claim. Empty ref_ids means a marker was found but
# could not be linked; that is recorded rather than dropped.
#
# Sections are flat with a level rather than nested. Nothing downstream walks a
# section tree, since the agent edits blocks and the diff compares blocks, so a
# tree would be structure maintained and never traversed.
#
# Block ids are positional at parse time and frozen afterwards. A block added
# by a later edit takes a freshly minted id rather than renumbering its
# neighbours, because the agent addresses blocks by id, the diff is keyed by
# id, and revisions are compared by id.
#
# `seq` is the monotonic counter for ids minted after parse time. It is
# serialised with the revision, since a counter living only in memory would
# hand out colliding ids after a restart.
#
# `style` is the single inferred field here. Everything else was read off the
# page; this one is guessed from a sample of markers, which is why it carries a
# confidence and defaults to "unknown" rather than to a plausible answer.
