from app.domain.document import Block, CiteNode, TextRun
from app.domain.edit import BlockPatch, OperationKind
from app.modules.editing.provider.invariant_provider import enforce, ref_counts
from app.modules.editing.provider.placeholder_provider import (
    deflate,
    inflate,
    reordered,
)

SENTENCE_ENDINGS = (".", "!", "?")


def apply_text(block: Block, new_text: str, operation: OperationKind) -> BlockPatch:
    deflated = deflate(block.inlines)
    rebuilt = inflate(new_text, deflated.nodes)

    delta = enforce(operation, ref_counts(block.inlines), ref_counts(rebuilt))
    delta.moved = reordered(deflated, new_text)

    return BlockPatch(
        block_id=block.id,
        operation=operation,
        before=block.inlines,
        after=rebuilt,
        before_text=deflated.text,
        after_text=new_text,
        citations=delta,
    )


def add_citation(block: Block, ref_id: str, node_id: str) -> BlockPatch:
    citation = CiteNode(id=node_id, ref_ids=[ref_id])
    rebuilt = _insert_before_final_stop(block.inlines, citation)

    delta = enforce("add_citation", ref_counts(block.inlines), ref_counts(rebuilt))

    return BlockPatch(
        block_id=block.id,
        operation="add_citation",
        before=block.inlines,
        after=rebuilt,
        before_text=deflate(block.inlines).text,
        after_text=deflate(rebuilt).text,
        citations=delta,
    )


def delete_block(block: Block) -> BlockPatch:
    delta = enforce("delete_block", ref_counts(block.inlines), {})

    return BlockPatch(
        block_id=block.id,
        operation="delete_block",
        before=block.inlines,
        after=[],
        before_text=deflate(block.inlines).text,
        after_text="",
        citations=delta,
        deleted=True,
    )


def _insert_before_final_stop(inlines: list, citation: CiteNode) -> list:
    if not inlines:
        return [citation]

    last = inlines[-1]
    if not isinstance(last, TextRun):
        return [*inlines, TextRun(text=" "), citation]

    stripped = last.text.rstrip()
    if not stripped.endswith(SENTENCE_ENDINGS):
        return [*inlines, TextRun(text=" "), citation]

    head = stripped[:-1].rstrip()
    tail = stripped[-1] + last.text[len(stripped) :]

    rebuilt = list(inlines[:-1])
    if head:
        rebuilt.append(TextRun(text=head + " "))
    rebuilt.append(citation)
    rebuilt.append(TextRun(text=tail))
    return rebuilt


# Notes
#
# Every operation is a pure function from a block to a BlockPatch, and every
# one of them runs both guards before returning. There is no path here that
# produces a patch without the placeholder round-trip and the count check
# having passed, which is what makes "an edit cannot silently break a citation"
# a property of the module rather than a discipline the caller has to remember.
#
# The two guards are applied in that order for a reason. inflate() fails first
# and says which markers were lost, which is the message a researcher can act
# on. enforce() then catches anything structural the marker check could not
# see, such as an operation whose declared rule does not match what it actually
# did to the counts.
#
# Nothing here calls a model. The writer produces a string somewhere else and
# hands it in, so the whole of this file is testable with a literal.
#
# add_citation places the marker before the final full stop rather than after
# it, because "...as shown in prior work [12]." is where a citation belongs and
# "...as shown in prior work. [12]" is not a sentence anyone wrote. It is a
# small piece of typographic judgement, and it lives in code rather than in a
# prompt precisely because it is deterministic.
#
# The new CiteNode carries exactly one ref_id. A citation act grouping several
# works, "[12, 13]", is something the author wrote and the parser preserved;
# the agent adding one source at a time keeps each insertion individually
# reviewable and individually reversible.
#
# before_text and after_text keep the markers visible rather than stripping
# them to prose. They are what the diff and the tests read, and a text pair
# that hid the citations would make the single most important thing about an
# edit, whether a citation moved, invisible in the representation of it.
#
# delete_block enforces against an empty count map rather than skipping the
# check. Deleting is allowed to lose citations, but it still has to declare
# them, and the losses come back in the patch so the user approves a deletion
# knowing exactly which sources leave the paper with it.
