from app.modules.review.provider.llm_backend import LlmBackend

SYSTEM = (
    "You edit one paragraph of a research paper at a time. The paragraph "
    "contains markers written as [[c_4]], [[x_2]] or [[m_1]]. Each marker "
    "stands for a citation, a figure or table reference, or a formula.\n\n"
    "Rules you must follow exactly:\n"
    "- Reproduce every marker from the input, once each, unchanged.\n"
    "- Never invent a marker that was not in the input.\n"
    "- Keep each marker beside the statement it belongs to. If you merge or "
    "shorten sentences, carry the marker along with the claim it supports.\n"
    "- Do not write citations yourself in any other form. No author names in "
    "brackets, no years in parentheses, no numbers in square brackets.\n"
    "- Preserve the author's meaning, terminology and voice. You are tightening "
    "their prose, not replacing it.\n\n"
    "Return only the edited paragraph text."
)

WRITE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {
        "text": {
            "type": "string",
            "description": "The edited paragraph, with every original marker preserved.",
        }
    },
}


class WriterProvider:
    def __init__(self, llm: LlmBackend) -> None:
        self._llm = llm

    async def shorten(self, text: str, target_ratio: float) -> str:
        target = max(1, int(len(text.split()) * target_ratio))
        return await self._write(
            f"Shorten this paragraph to about {target} words, keeping every "
            f"marker.\n\n{text}"
        )

    async def rewrite(self, text: str, instruction: str) -> str:
        return await self._write(
            f"Edit this paragraph as follows: {instruction}\n\n{text}"
        )

    async def _write(self, user: str) -> str:
        payload = await self._llm.complete_json(
            system=SYSTEM,
            user=user,
            schema=WRITE_SCHEMA,
            schema_name="edited_paragraph",
        )
        return (payload.get("text") or "").strip()


# Notes
#
# The writer sees one paragraph and nothing else. It has no access to the
# document, the library, the plan or the other blocks, so the blast radius of a
# bad completion is one block that then has to pass two independent checks.
#
# What it receives is already deflated: citations, cross-references and
# formulas have been replaced by opaque markers by placeholder_provider. The
# rules in the system prompt ask it to preserve them, but nothing here depends
# on it obeying. If it drops, invents or repeats a marker, inflate() refuses
# the result and the user is told which markers were lost. The prompt is a
# request; the round-trip check is the guarantee.
#
# "Do not write citations yourself in any other form" is the one rule that
# guards something the marker check cannot see. A model that writes "(Smith,
# 2019)" as ordinary prose has not broken any marker, but it has put an
# unverifiable citation into the paper as plain text. Style detection and the
# extraction invariant both assume prose contains no citation markers, so this
# keeps that true after an edit as well.
#
# The word target for a shorten is computed here rather than asked for as a
# percentage. Models are much better at "about 40 words" than at "70% of the
# original length", and the caller keeps a ratio because that is what the plan
# expresses.
#
# The response is JSON with one string field rather than raw text, so this
# backend has exactly one method shape across every call in the codebase and
# providers with constrained decoding can enforce it.
