from app.domain.review import Sentence
from app.modules.review.provider.llm_backend import LlmBackend

SCHEMA_NAME = "uncited_claims"

SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "needs_citation": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["index", "needs_citation", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}

SYSTEM = """You review academic papers for missing citations.

You are given numbered sentences taken from one paper. None of them currently
carry a citation. For each sentence, decide whether it makes a factual claim
about prior work, established results, or empirical facts that a reader would
expect to be supported by a reference.

Answer true only when a citation is genuinely expected:
- claims about what prior work showed, proposed or found
- statements of established fact the authors did not demonstrate here
- comparisons to other methods, systems or results
- attributed numbers, datasets or benchmarks

Answer false for everything else, including:
- statements about what THIS paper does, proposes, or will show
- descriptions of the authors' own method, model, experiments or results
- definitions of notation, section signposting, transitions
- hedged or general observations that assert nothing checkable

Be conservative. Flagging a sentence that needs no citation wastes the
author's time and is worse than missing a borderline one.

Refer to sentences only by the index given. Do not invent sentences."""

MAX_SENTENCES_PER_CALL = 20
MIN_CLAIM_CHARS = 40


class ClaimProvider:
    def __init__(self, llm: LlmBackend) -> None:
        self._llm = llm

    async def find_uncited_claims(
        self,
        sentences: list[Sentence],
        limit: int | None = None,
        skip_block_ids: set[str] | None = None,
    ) -> list[Sentence]:
        excluded = skip_block_ids or set()

        candidates = [
            sentence
            for sentence in sentences
            if not sentence.is_cited
            and len(sentence.text) >= MIN_CLAIM_CHARS
            and sentence.block_id not in excluded
        ]
        if not candidates:
            return []

        flagged: list[Sentence] = []
        for batch in self._batches(candidates):
            flagged.extend(await self._judge(batch))
            if limit is not None and len(flagged) >= limit:
                return flagged[:limit]
        return flagged

    def _batches(self, sentences: list[Sentence]) -> list[list[Sentence]]:
        return [
            sentences[start : start + MAX_SENTENCES_PER_CALL]
            for start in range(0, len(sentences), MAX_SENTENCES_PER_CALL)
        ]

    async def _judge(self, batch: list[Sentence]) -> list[Sentence]:
        listing = "\n".join(
            f"[{index}] {sentence.text}" for index, sentence in enumerate(batch)
        )

        payload = await self._llm.complete_json(
            system=SYSTEM,
            user=f"Sentences:\n\n{listing}",
            schema=SCHEMA,
            schema_name=SCHEMA_NAME,
            max_tokens=2048,
        )

        flagged: list[Sentence] = []
        for entry in payload.get("claims") or []:
            index = entry.get("index")
            if not isinstance(index, int) or not (0 <= index < len(batch)):
                continue
            if entry.get("needs_citation") is True:
                flagged.append(batch[index])
        return flagged
