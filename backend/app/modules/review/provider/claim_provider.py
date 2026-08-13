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


# Notes
#
# Pass A. The model classifies sentences it is shown; it never produces them.
# Answers come back as an index into the batch, and an index outside the batch
# is discarded rather than trusted, so a finding can only ever attach to a
# sentence that genuinely exists in the document.
#
# That constraint is the reason this pass is shaped as classification rather
# than extraction. Asking a model to "find the claims" returns paraphrased text
# with no offsets, and the finding then points at nothing the UI can highlight.
#
# The prompt spends most of its length on what NOT to flag, because the obvious
# failure mode is flagging every sentence. Papers are full of statements about
# the authors' own work, notation and signposting, none of which want a
# citation. A reviewer that marks forty sentences on a forty-sentence paper is
# useless, so the instruction is explicitly to be conservative and the cost of
# a false positive is stated.
#
# Only uncited sentences are considered. A sentence that already carries a
# citation is stage C's problem, and asking whether it needs one would be
# answering a question nobody asked.
#
# Very short sentences are skipped before any model call. Fragments left by the
# splitter, headings that ended up as prose and one-clause transitions are
# never claims, and filtering them in code costs nothing and shrinks every
# prompt.
#
# Sentences are batched because one call per sentence would mean hundreds of
# requests per paper. Batching also gives the model surrounding context, which
# makes "this describes the authors' own method" much easier to see than it is
# from a single sentence in isolation.
#
# The limit stops batching as soon as enough claims have been found, rather
# than judging the whole paper and discarding the surplus afterwards. A long
# paper has hundreds of uncited sentences, which is twenty or more model calls
# to produce a list nobody reads past the top of, and free tiers rate limit on
# exactly that kind of burst.
#
# Stopping early biases the results toward the front of the paper, which is
# where the introduction and related work sit. That is the right bias for this
# particular check: those sections are where uncited claims about prior work
# actually live, while later sections describe the authors' own results and
# should not be citing anyone.
