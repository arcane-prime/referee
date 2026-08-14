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
