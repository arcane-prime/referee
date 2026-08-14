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
