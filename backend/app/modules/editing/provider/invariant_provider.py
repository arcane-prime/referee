from app.domain.document import CiteNode, Document, Inline
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


def document_delta(before: Document, after: Document) -> CitationDelta:
    return compare(before.ref_id_counts(), after.ref_id_counts())


def _describe(delta: CitationDelta) -> str:
    parts: list[str] = []
    if delta.removed:
        parts.append(f"would drop {', '.join(sorted(set(delta.removed)))}")
    if delta.added:
        parts.append(f"would add {', '.join(sorted(set(delta.added)))}")
    return " and ".join(parts)


# Notes
#
# This is the second guard on the same property, and it is deliberately
# independent of the first. The placeholder layer is per block and structural:
# it works by never letting the model touch a citation. This one is whole
# document and arithmetic: it counts ref ids before and after and compares them
# against what the operation was allowed to do. A bug in either does not
# disable the other.
#
# COUNT_RULES lives in domain/edit.py next to the operations rather than here,
# so adding an operation forces a decision about what it may do to citations.
# An operation with no rule is refused rather than defaulted, because "may this
# silently drop citations?" is not a question anyone should get to leave blank.
#
# compare() counts multiplicity rather than membership. Citing ref_12 twice and
# citing it once are different claims about the paper, and a set difference
# would call them the same.
#
# check_citable is the anti-fabrication gate and it is a lookup, not a
# judgement. A new citation must name a reference that is already in the
# library and that came back from OpenAlex or Semantic Scholar carrying a real
# external id. A model cannot talk its way past this: an id it invented is not
# in the library, and a reference merely parsed out of the user's own PDF has
# provenance "parsed_from_pdf" and fails the second half. That is why "never
# hallucinated" is a property of the types here rather than an instruction in a
# prompt.
#
# Violations carry a sentence a researcher can read, naming the actual ref ids.
# The user is going to see this text when an edit is refused, and "invariant
# violation in enforce()" would tell them nothing about their paper.
