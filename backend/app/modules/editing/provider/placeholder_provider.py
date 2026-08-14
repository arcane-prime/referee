import re
from dataclasses import dataclass

from app.domain.document import Inline, TextRun

TOKEN_PATTERN = re.compile(r"\[\[([A-Za-z0-9_]+)\]\]")


class PlaceholderMismatch(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def token_for(node_id: str) -> str:
    return f"[[{node_id}]]"


@dataclass(frozen=True)
class DeflatedBlock:
    text: str
    nodes: dict[str, Inline]

    @property
    def tokens(self) -> set[str]:
        return set(self.nodes)

    @property
    def order(self) -> list[str]:
        return TOKEN_PATTERN.findall(self.text)


def deflate(inlines: list[Inline]) -> DeflatedBlock:
    parts: list[str] = []
    nodes: dict[str, Inline] = {}

    for node in inlines:
        if isinstance(node, TextRun):
            parts.append(node.text)
            continue

        if node.id in nodes:
            raise PlaceholderMismatch(
                f"Block contains two nodes with the id '{node.id}', so its "
                f"citations cannot be tracked through an edit."
            )

        nodes[node.id] = node
        parts.append(token_for(node.id))

    return DeflatedBlock(text="".join(parts), nodes=nodes)


def verify(text: str, expected: set[str]) -> None:
    found = TOKEN_PATTERN.findall(text)
    seen = set(found)

    missing = sorted(expected - seen)
    if missing:
        raise PlaceholderMismatch(
            f"The rewrite dropped {len(missing)} citation or reference marker(s): "
            f"{', '.join(missing)}. The edit was refused rather than applied."
        )

    unknown = sorted(seen - expected)
    if unknown:
        raise PlaceholderMismatch(
            f"The rewrite invented {len(unknown)} marker(s) that were not in the "
            f"original text: {', '.join(unknown)}."
        )

    duplicated = sorted({token for token in found if found.count(token) > 1})
    if duplicated:
        raise PlaceholderMismatch(
            f"The rewrite repeated {len(duplicated)} marker(s): "
            f"{', '.join(duplicated)}. A citation cannot appear twice from one "
            f"original."
        )


def inflate(text: str, nodes: dict[str, Inline]) -> list[Inline]:
    verify(text, set(nodes))

    rebuilt: list[Inline] = []
    cursor = 0

    for match in TOKEN_PATTERN.finditer(text):
        before = text[cursor : match.start()]
        if before:
            rebuilt.append(TextRun(text=before))
        rebuilt.append(nodes[match.group(1)])
        cursor = match.end()

    tail = text[cursor:]
    if tail:
        rebuilt.append(TextRun(text=tail))

    return rebuilt


def reordered(before: DeflatedBlock, after_text: str) -> list[str]:
    was = before.order
    now = TOKEN_PATTERN.findall(after_text)

    if was == now:
        return []
    return sorted(set(was) & set(now))


# Notes
#
# This is the piece the whole stage rests on, and it is deliberately the piece
# with no network, no model and no I/O in it.
#
# The model is never shown a block. It is shown the block's prose with every
# citation, cross-reference and formula replaced by an opaque token, and the
# tokens are its contract: whatever it returns must contain the same set. Then
# inflate() rebuilds the inline list using the original node objects, so the
# model chose where [[c_4]] sits and could not touch what [[c_4]] is.
#
# A citation therefore cannot be reworded, retargeted or invented, because it
# was never text in the model's input. It can still move, which is required
# rather than tolerated: the brief asks that citations stay attached to the
# right context when text shrinks, and a citation that could not move would be
# stranded next to a sentence that no longer exists.
#
# The token carries the node's own id rather than an index. An index would be
# stable only until an operation reordered anything, and a mismatch would then
# be silently wrong instead of loudly wrong.
#
# verify() refuses rather than repairs, and the order of its three checks is
# the order of how much damage each represents. A missing token means a
# citation would have been dropped, which is the exact failure the brief calls
# non-negotiable. An unknown token means the model wrote something that looks
# like a citation marker, which is fabrication wearing our own syntax. A
# duplicate means one original citation would become two, quietly changing what
# the paper claims to cite.
#
# Repairing any of these would mean guessing what the author meant. Refusing
# the operation and telling the user which markers were lost is both honest and
# more useful, and it is why the failure path returns a reason string rather
# than a bare exception type.
#
# deflate() rejects a block holding two nodes with the same id. That should be
# impossible from extraction, but the whole guarantee here is keyed on node
# ids, so the one case that would break it silently is checked rather than
# assumed.
#
# reordered() reports which markers changed position rather than which changed
# index. Every index moves when prose is rewritten, so index churn would flag
# everything and mean nothing; a changed sequence is the thing a reader would
# actually call a move.
