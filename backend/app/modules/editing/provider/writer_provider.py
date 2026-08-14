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
