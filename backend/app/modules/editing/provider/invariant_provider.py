from app.domain.document import CiteNode, Inline
from app.domain.edit import COUNT_RULES, CitationDelta, OperationKind
from app.domain.library import Library


class InvariantViolation(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def ref_counts(inlines: list[Inline]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in inlines:
        if not isinstance(node, CiteNode):
            continue
        for ref_id in node.ref_ids:
            counts[ref_id] = counts.get(ref_id, 0) + 1
    return counts


def compare(before: dict[str, int], after: dict[str, int]) -> CitationDelta:
    added: list[str] = []
    removed: list[str] = []

    for ref_id in sorted(set(before) | set(after)):
        was = before.get(ref_id, 0)
        now = after.get(ref_id, 0)
        if now > was:
            added.extend([ref_id] * (now - was))
        elif now < was:
            removed.extend([ref_id] * (was - now))

    return CitationDelta(added=added, removed=removed)


def enforce(
    operation: OperationKind,
    before: dict[str, int],
    after: dict[str, int],
) -> CitationDelta:
    rule = COUNT_RULES.get(operation)
    if rule is None:
        raise InvariantViolation(
            f"Operation '{operation}' declares no citation rule, so it is not "
            f"allowed to touch the document."
        )

    delta = compare(before, after)

    if rule == "identical" and (delta.added or delta.removed):
        raise InvariantViolation(
            f"A '{operation}' must leave every citation in place, but this one "
            f"{_describe(delta)}."
        )

    if rule == "may_increase" and delta.removed:
        raise InvariantViolation(
            f"A '{operation}' may only add citations, but this one would remove "
            f"{', '.join(sorted(set(delta.removed)))}."
        )

    return delta


def check_citable(library: Library, ref_id: str) -> None:
    reference = library.get(ref_id)

    if reference is None:
        raise InvariantViolation(
            f"Reference '{ref_id}' is not in this paper's library, so it cannot "
            f"be cited."
        )

    if not reference.can_be_cited_by_the_agent:
        raise InvariantViolation(
            f"Reference '{ref_id}' was read off the PDF rather than fetched from "
            f"a database, so there is no verified record behind it and the agent "
            f"may not cite it."
        )


def _describe(delta: CitationDelta) -> str:
    parts: list[str] = []
    if delta.removed:
        parts.append(f"would drop {', '.join(sorted(set(delta.removed)))}")
    if delta.added:
        parts.append(f"would add {', '.join(sorted(set(delta.added)))}")
    return " and ".join(parts)
