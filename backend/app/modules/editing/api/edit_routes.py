from fastapi import APIRouter, Depends, status

from app.modules.editing.api.dependencies import (
    get_edit_provider,
    get_revision_provider,
)
from app.modules.editing.dto.edit_dto import (
    AppliedDto,
    ApplyEditDto,
    CurrentDocumentDto,
    EditCommandDto,
    ProposalDto,
)
from app.modules.editing.provider.edit_provider import EditProvider
from app.modules.editing.provider.revision_provider import RevisionProvider

router = APIRouter(tags=["editing"])


@router.get(
    "/papers/{paper_id}/document",
    response_model=CurrentDocumentDto,
    status_code=status.HTTP_200_OK,
    summary="Read the paper at its latest revision, or at a specific one",
)
async def read_document(
    paper_id: str,
    revision: int | None = None,
    revisions: RevisionProvider = Depends(get_revision_provider),
) -> CurrentDocumentDto:
    document, number = revisions.load(paper_id, revision)

    return CurrentDocumentDto(
        paper_id=paper_id,
        revision=number,
        available_revisions=revisions.available(paper_id),
        document=document,
    )


@router.post(
    "/papers/{paper_id}/edit/plan",
    response_model=ProposalDto,
    status_code=status.HTTP_200_OK,
    summary="Turn a natural-language command into a reviewable set of changes",
)
async def plan_edit(
    paper_id: str,
    body: EditCommandDto,
    editing: EditProvider = Depends(get_edit_provider),
) -> ProposalDto:
    proposal = await editing.propose(paper_id=paper_id, command=body.command)

    return ProposalDto(
        proposal=proposal,
        applicable=not proposal.is_empty,
        message=_describe(proposal),
    )


@router.post(
    "/papers/{paper_id}/edit/apply",
    response_model=AppliedDto,
    status_code=status.HTTP_200_OK,
    summary="Approve prepared changes and write the next revision",
)
async def apply_edit(
    paper_id: str,
    body: ApplyEditDto,
    editing: EditProvider = Depends(get_edit_provider),
) -> AppliedDto:
    applied = editing.apply(
        paper_id=paper_id,
        proposal=body.proposal,
        approved=set(body.approved) if body.approved is not None else None,
    )

    return AppliedDto(
        applied=applied,
        message=(
            f"Applied {len(applied.applied_blocks)} change(s) as revision "
            f"{applied.revision}. Revision {applied.base_revision} is unchanged "
            f"on disk."
        ),
    )


def _describe(proposal) -> str | None:
    if proposal.note:
        return proposal.note

    if proposal.is_empty and proposal.rejected:
        return (
            "Every change was refused because it would have altered the "
            "paper's citations. Nothing was applied."
        )

    if proposal.is_empty:
        return "Nothing in the paper matched that instruction."

    if proposal.rejected:
        return (
            f"{len(proposal.patches)} change(s) ready. "
            f"{len(proposal.rejected)} were refused because they would have "
            f"altered the paper's citations."
        )

    return f"{len(proposal.patches)} change(s) ready for review."
