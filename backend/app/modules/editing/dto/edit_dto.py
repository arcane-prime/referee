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


# Notes
#
# The proposal goes out to the browser and comes back on apply. That makes it
# user input on the way back, which is why apply() re-verifies it against the
# document on disk rather than trusting it. Sending it round rather than
# holding it in server memory keeps the API stateless and means a proposal
# cannot expire because a process restarted.
#
# `approved` is a list of block ids rather than a flag, so a researcher can
# accept the two changes they liked and drop the third. Omitting it means every
# patch in the proposal.
#
# `applicable` is computed rather than left for the client to work out from an
# empty patch list. Whether there is anything to approve is a question the
# server can answer definitively, and duplicating that rule in the UI is how
# the two come to disagree.
#
# The command is length limited because it is a sentence of instruction, not a
# document. An unbounded string here would be a way to push arbitrary text into
# a model prompt.
#
# CurrentDocumentDto exists so the UI can re-read the paper after an edit
# without re-running extraction. Re-extracting would call GROBID and the
# literature databases again to produce a document already sitting on disk.
#
# available_revisions is returned alongside the current one because the history
# is the feature. Revisions are append-only, so listing them is what makes
# "show me the paper before that edit" a read rather than an undo operation.
