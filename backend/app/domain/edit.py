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


# Notes
#
# An edit is a value before it is an action. A command produces a
# RevisionProposal, which is a thing the user can read and decline; only a
# second, explicit request turns one into a revision on disk. That is the
# brief's "show the changes for the user to approve" expressed in the types
# rather than only in the UI.
#
# Operations are a discriminated union on `kind`, the same shape as Inline in
# document.py. The planner's whole output is one of these objects, so a model
# that produces nonsense produces a validation error rather than a damaged
# paper. There is no free-text field anywhere in an operation that gets applied
# to the document; `instruction` is passed to the writer, never executed.
#
# COUNT_RULES is the table the invariant checker enforces, kept next to the
# operations rather than inside the checker so that adding an operation forces
# a decision about what it is allowed to do to the citation counts. An
# operation with no rule is refused rather than defaulted, since the safe
# default for "may this drop citations?" is not a value anyone should get to
# omit.
#
# BlockPatch carries both the inline lists and their plain text. The lists are
# what gets applied; the text is what the diff renders. Deriving the text at
# render time instead would mean the UI reimplementing how nodes flatten, and
# the two would drift.
#
# CitationDelta separates moved from added and removed on purpose. A citation
# moving is normal and expected during a shorten - the brief requires that
# citations follow their claim when text shrinks - while one being added or
# removed is a decision the user must see. Collapsing all three into "changed"
# would bury the only two cases that matter.
#
# RejectedOperation exists so a refused edit is reported rather than silently
# skipped. If the writer returned text that would have dropped a citation, the
# user is told exactly that, for that block, with the reason. An edit that
# quietly does less than it claimed is the failure mode this whole stage is
# built to prevent.
#
# `base_revision` is recorded on both the proposal and the applied revision so
# a proposal computed against rev_2 cannot be applied on top of rev_3. Two
# commands issued from two tabs would otherwise interleave into a document
# neither of them describes.
