from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.domain.document import Inline

MIN_SHORTEN_RATIO = 0.2
MAX_SHORTEN_RATIO = 0.95


class ShortenBlock(BaseModel):
    kind: Literal["shorten_block"] = "shorten_block"
    block_id: str
    target_ratio: float = Field(default=0.7, ge=MIN_SHORTEN_RATIO, le=MAX_SHORTEN_RATIO)


class RewriteBlock(BaseModel):
    kind: Literal["rewrite_block"] = "rewrite_block"
    block_id: str
    instruction: str


class AddCitation(BaseModel):
    kind: Literal["add_citation"] = "add_citation"
    block_id: str
    ref_id: str
    after_sentence: int | None = None


class DeleteBlock(BaseModel):
    kind: Literal["delete_block"] = "delete_block"
    block_id: str


EditOperation = Annotated[
    ShortenBlock | RewriteBlock | AddCitation | DeleteBlock,
    Field(discriminator="kind"),
]

OperationKind = Literal["shorten_block", "rewrite_block", "add_citation", "delete_block"]

CountRule = Literal["identical", "may_increase", "may_decrease"]

COUNT_RULES: dict[str, CountRule] = {
    "shorten_block": "identical",
    "rewrite_block": "identical",
    "add_citation": "may_increase",
    "delete_block": "may_decrease",
}


class EditPlan(BaseModel):
    command: str
    intent: str
    scope: str | None = None
    operations: list[EditOperation] = Field(default_factory=list)
    note: str | None = None


class CitationDelta(BaseModel):
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    moved: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.moved)


class BlockPatch(BaseModel):
    block_id: str
    operation: OperationKind
    before: list[Inline] = Field(default_factory=list)
    after: list[Inline] = Field(default_factory=list)
    before_text: str = ""
    after_text: str = ""
    citations: CitationDelta = Field(default_factory=CitationDelta)
    deleted: bool = False


class RejectedOperation(BaseModel):
    block_id: str
    operation: OperationKind
    reason: str


class RevisionProposal(BaseModel):
    paper_id: str
    base_revision: int
    command: str
    intent: str
    patches: list[BlockPatch] = Field(default_factory=list)
    rejected: list[RejectedOperation] = Field(default_factory=list)
    citations: CitationDelta = Field(default_factory=CitationDelta)
    note: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.patches

    @property
    def loses_citations(self) -> bool:
        return bool(self.citations.removed)


class AppliedRevision(BaseModel):
    paper_id: str
    revision: int
    base_revision: int
    command: str
    applied_blocks: list[str] = Field(default_factory=list)
    citations: CitationDelta = Field(default_factory=CitationDelta)
