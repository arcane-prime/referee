from pydantic import BaseModel, Field

from app.domain.document import Document
from app.domain.edit import AppliedRevision, RevisionProposal

MAX_COMMAND_CHARS = 500


class CurrentDocumentDto(BaseModel):
    paper_id: str
    revision: int
    available_revisions: list[int]
    document: Document


class EditCommandDto(BaseModel):
    command: str = Field(min_length=1, max_length=MAX_COMMAND_CHARS)


class ApplyEditDto(BaseModel):
    proposal: RevisionProposal
    approved: list[str] | None = None


class ProposalDto(BaseModel):
    proposal: RevisionProposal
    applicable: bool
    message: str | None = None


class AppliedDto(BaseModel):
    applied: AppliedRevision
    message: str
