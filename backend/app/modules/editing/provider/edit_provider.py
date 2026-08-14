from app.core.exceptions import EditConflictError, EditRefusedError
from app.domain.document import Block, Document
from app.domain.edit import (
    AppliedRevision,
    BlockPatch,
    CitationDelta,
    RejectedOperation,
    RevisionProposal,
)
from app.domain.library import Library
from app.modules.editing.provider import operation_provider
from app.modules.editing.provider.invariant_provider import (
    InvariantViolation,
    check_citable,
    enforce,
    ref_counts,
)
from app.modules.editing.provider.placeholder_provider import (
    PlaceholderMismatch,
    deflate,
)
from app.modules.editing.provider.plan_provider import PlanProvider
from app.modules.editing.provider.revision_provider import RevisionProvider
from app.modules.editing.provider.writer_provider import WriterProvider


class EditProvider:
    def __init__(
        self,
        revisions: RevisionProvider,
        planner: PlanProvider,
        writer: WriterProvider,
    ) -> None:
        self._revisions = revisions
        self._planner = planner
        self._writer = writer

    async def propose(self, paper_id: str, command: str) -> RevisionProposal:
        document, revision = self._revisions.load(paper_id)
        library = self._revisions.load_library(paper_id)

        plan = await self._planner.plan(document, command)

        patches: list[BlockPatch] = []
        rejected: list[RejectedOperation] = []
        minted = document.seq

        for operation in plan.operations:
            block = document.block(operation.block_id)
            if block is None:
                continue

            try:
                patch, minted = await self._run(operation, block, library, minted)
            except (PlaceholderMismatch, InvariantViolation) as refusal:
                rejected.append(
                    RejectedOperation(
                        block_id=operation.block_id,
                        operation=operation.kind,
                        reason=refusal.reason,
                    )
                )
                continue

            if patch is not None:
                patches.append(patch)

        return RevisionProposal(
            paper_id=paper_id,
            base_revision=revision,
            command=command,
            intent=plan.intent,
            patches=patches,
            rejected=rejected,
            citations=_total(patches),
            note=plan.note,
        )

    def apply(
        self,
        paper_id: str,
        proposal: RevisionProposal,
        approved: set[str] | None = None,
    ) -> AppliedRevision:
        document, revision = self._revisions.load(paper_id)

        if proposal.base_revision != revision:
            raise EditConflictError(
                f"These changes were prepared against revision "
                f"{proposal.base_revision}, but the paper is now at revision "
                f"{revision}. Run the command again to see the changes against "
                f"the current text."
            )

        wanted = [
            patch
            for patch in proposal.patches
            if approved is None or patch.block_id in approved
        ]
        if not wanted:
            raise EditRefusedError("No changes were approved, so nothing was written.")

        for patch in wanted:
            self._verify_against_disk(document, patch)

        applied: list[str] = []
        for patch in wanted:
            self._write_patch(document, patch)
            applied.append(patch.block_id)

        document.seq = max(document.seq, _highest_minted(wanted))
        next_revision = revision + 1
        self._revisions.save(paper_id, document, next_revision)

        return AppliedRevision(
            paper_id=paper_id,
            revision=next_revision,
            base_revision=revision,
            command=proposal.command,
            applied_blocks=applied,
            citations=_total(wanted),
        )

    async def _run(
        self,
        operation,
        block: Block,
        library: Library,
        minted: int,
    ) -> tuple[BlockPatch | None, int]:
        if operation.kind == "shorten_block":
            deflated = deflate(block.inlines)
            text = await self._writer.shorten(deflated.text, operation.target_ratio)
            return operation_provider.apply_text(block, text, "shorten_block"), minted

        if operation.kind == "rewrite_block":
            deflated = deflate(block.inlines)
            text = await self._writer.rewrite(deflated.text, operation.instruction)
            return operation_provider.apply_text(block, text, "rewrite_block"), minted

        if operation.kind == "add_citation":
            check_citable(library, operation.ref_id)
            minted += 1
            patch = operation_provider.add_citation(
                block, operation.ref_id, f"c_e{minted}"
            )
            return patch, minted

        if operation.kind == "delete_block":
            return operation_provider.delete_block(block), minted

        return None, minted

    @staticmethod
    def _verify_against_disk(document: Document, patch: BlockPatch) -> None:
        block = document.block(patch.block_id)

        if block is None:
            raise EditConflictError(
                f"Block '{patch.block_id}' is no longer in the paper, so this "
                f"change cannot be applied."
            )

        if block.inlines != patch.before:
            raise EditConflictError(
                f"Block '{patch.block_id}' has changed since these changes were "
                f"prepared. Run the command again."
            )

        try:
            enforce(patch.operation, ref_counts(patch.before), ref_counts(patch.after))
        except InvariantViolation as refusal:
            raise EditRefusedError(refusal.reason) from refusal

    @staticmethod
    def _write_patch(document: Document, patch: BlockPatch) -> None:
        for section in document.sections:
            for index, block in enumerate(section.blocks):
                if block.id != patch.block_id:
                    continue
                if patch.deleted:
                    section.blocks.pop(index)
                else:
                    block.inlines = patch.after
                return


def _total(patches: list[BlockPatch]) -> CitationDelta:
    total = CitationDelta()
    for patch in patches:
        total.added.extend(patch.citations.added)
        total.removed.extend(patch.citations.removed)
        total.moved.extend(patch.citations.moved)
    return total


def _highest_minted(patches: list[BlockPatch]) -> int:
    highest = 0
    for patch in patches:
        for node in patch.after:
            if getattr(node, "id", "").startswith("c_e"):
                try:
                    highest = max(highest, int(node.id[3:]))
                except ValueError:
                    continue
    return highest


# Notes
#
# propose() and apply() are two calls because a proposal is a value the user
# can decline. propose() writes nothing at all: it loads a revision, asks the
# planner what to do, runs each operation, and returns what would happen. Only
# apply() touches the disk, and only for the blocks the user approved.
#
# A refused operation does not fail the request. If the writer returned text
# that would have dropped a citation, that one operation becomes a
# RejectedOperation carrying the reason, and the operations that succeeded are
# still offered. An edit that quietly did less than it claimed is the failure
# this stage exists to prevent; an edit that did four of five things and said
# so is useful.
#
# apply() re-checks everything rather than trusting the proposal it was handed.
# The proposal travels to the browser and back, so by the time it returns it is
# user input. Three things are verified: the base revision still matches, every
# targeted block still holds exactly the inlines the patch was computed from,
# and the citation counts still satisfy the operation's rule. A tampered
# `after` list that dropped a citation fails the third check; a stale proposal
# fails the first two.
#
# Comparing block.inlines to patch.before is a full structural comparison, not
# an id or a hash. It is the cheapest way to be certain the text being replaced
# is the text the user actually read and approved.
#
# New citation nodes are minted as c_e1, c_e2 from the document's own counter,
# so an id created by an edit can never collide with one the parser assigned.
# The counter is advanced on the document before saving, which is why it is
# serialised with the revision: a counter living only in memory hands out
# colliding ids after a restart.
#
# The planner and writer are injected rather than constructed here, so the
# whole orchestrator runs against the stub backend with no key and no network.
