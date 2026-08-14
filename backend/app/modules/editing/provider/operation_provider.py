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
