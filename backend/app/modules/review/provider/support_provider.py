import re

from app.domain.library import Reference
from app.domain.review import Evidence, Sentence, SupportGrade
from app.modules.review.provider.llm_backend import LlmBackend

SCHEMA_NAME = "claim_support"

GRADES = ["supports", "partially_supports", "not_supported", "insufficient_evidence"]

SCHEMA = {
    "type": "object",
    "properties": {
        "quote": {"type": "string"},
        "grade": {"type": "string", "enum": GRADES},
        "note": {"type": "string"},
    },
    "required": ["quote", "grade", "note"],
    "additionalProperties": False,
}

SYSTEM = """You check whether a cited source supports a claim.

You are given one CLAIM from a paper and the ABSTRACT of a work it cites.

Follow this order, and do not depart from it:

1. First find a span of text in the ABSTRACT that bears on the claim, and copy
   it into "quote" EXACTLY as it appears, character for character. Copy it;
   do not paraphrase, summarise, correct or shorten it.
2. Only then choose a grade, judging solely by the quote you copied.

If the abstract contains nothing relevant to the claim, return an empty quote
and the grade "insufficient_evidence".

Grades:
- supports              the quote states or clearly implies the claim
- partially_supports    the quote is related but weaker, narrower, or hedged
- not_supported         the quote contradicts the claim
- insufficient_evidence the abstract does not address the claim

An abstract is a summary, so it often will not mention a specific detail. That
is "insufficient_evidence", not "not_supported". Reserve "not_supported" for a
genuine contradiction.

Keep "note" to one short sentence."""

WHITESPACE = re.compile(r"\s+")
MIN_QUOTE_CHARS = 12
MAX_ABSTRACT_CHARS = 4000


def normalise_for_matching(value: str) -> str:
    return WHITESPACE.sub(" ", value).strip().lower()


def quote_is_verbatim(quote: str, abstract: str) -> bool:
    if not quote or not abstract:
        return False
    if len(quote.strip()) < MIN_QUOTE_CHARS:
        return False
    return normalise_for_matching(quote) in normalise_for_matching(abstract)


class SupportProvider:
    def __init__(self, llm: LlmBackend) -> None:
        self._llm = llm

    async def check(self, sentence: Sentence, reference: Reference) -> Evidence | None:
        abstract = reference.resolution.abstract
        if not abstract:
            return None

        csl = reference.csl
        evidence = Evidence(
            ref_id=reference.id,
            source_title=csl.title if csl else None,
            source_doi=reference.doi,
            source_url=f"https://doi.org/{reference.doi}" if reference.doi else None,
        )

        payload = await self._llm.complete_json(
            system=SYSTEM,
            user=(
                f"CLAIM:\n{sentence.text}\n\n"
                f"ABSTRACT:\n{abstract[:MAX_ABSTRACT_CHARS]}"
            ),
            schema=SCHEMA,
            schema_name=SCHEMA_NAME,
            max_tokens=800,
        )

        quote = (payload.get("quote") or "").strip()
        grade = payload.get("grade")
        note = (payload.get("note") or "").strip() or None

        verified = quote_is_verbatim(quote, abstract)

        evidence.quote = quote or None
        evidence.quote_verified = verified
        evidence.note = note
        evidence.grade = self._final_grade(grade, verified)

        if not verified and quote:
            evidence.note = (
                "The model's quote was not found verbatim in the abstract, so this "
                "was downgraded to insufficient evidence."
            )

        return evidence

    @staticmethod
    def _final_grade(grade: object, quote_verified: bool) -> SupportGrade:
        if not quote_verified:
            return "insufficient_evidence"
        if grade in GRADES:
            return grade  # type: ignore[return-value]
        return "insufficient_evidence"
