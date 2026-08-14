from pydantic import ValidationError

from app.domain.document import Document
from app.domain.edit import EditPlan
from app.modules.review.provider.llm_backend import LlmBackend

MAX_OPERATIONS = 8
MAX_BLOCKS_OFFERED = 120
PLAN_MAX_TOKENS = 4096

SYSTEM = (
    "You plan edits to a research paper. You never write prose and you never "
    "write citations. You choose which blocks an instruction applies to and "
    "which operation each one needs. Choose the smallest set of blocks that "
    "satisfies the instruction. If the instruction names a section, only "
    "choose blocks from that section. If nothing in the paper matches the "
    "instruction, return no operations and say why in `note`."
)

PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent", "operations", "note"],
    "properties": {
        "intent": {
            "type": "string",
            "description": "A short restatement of what the user asked for.",
        },
        "scope": {
            "type": ["string", "null"],
            "description": "The section the instruction applies to, if it named one.",
        },
        "note": {
            "type": ["string", "null"],
            "description": "Why no operations were chosen, when none were.",
        },
        "operations": {
            "type": "array",
            "maxItems": MAX_OPERATIONS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "block_id"],
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": [
                            "shorten_block",
                            "rewrite_block",
                            "add_citation",
                            "delete_block",
                        ],
                    },
                    "block_id": {"type": "string"},
                    "target_ratio": {
                        "type": ["number", "null"],
                        "description": "For shorten_block: fraction of the original length to keep.",
                    },
                    "instruction": {
                        "type": ["string", "null"],
                        "description": "For rewrite_block: what to change about this block.",
                    },
                    "ref_id": {
                        "type": ["string", "null"],
                        "description": "For add_citation: which library reference to cite.",
                    },
                },
            },
        },
    },
}


class PlanProvider:
    def __init__(self, llm: LlmBackend) -> None:
        self._llm = llm

    async def plan(self, document: Document, command: str) -> EditPlan:
        payload = await self._llm.complete_json(
            system=SYSTEM,
            user=self._prompt(document, command),
            schema=PLAN_SCHEMA,
            schema_name="edit_plan",
            max_tokens=PLAN_MAX_TOKENS,
        )

        operations = [
            cleaned
            for cleaned in (self._clean(raw) for raw in payload.get("operations") or [])
            if cleaned is not None
        ]

        known = {block.id for block in document.blocks()}
        operations = [op for op in operations if op.get("block_id") in known]

        try:
            return EditPlan(
                command=command,
                intent=payload.get("intent") or command,
                scope=payload.get("scope"),
                note=payload.get("note"),
                operations=operations[:MAX_OPERATIONS],
            )
        except ValidationError:
            return EditPlan(
                command=command,
                intent=payload.get("intent") or command,
                note="The plan could not be read as a valid set of operations.",
            )

    @staticmethod
    def _clean(raw: dict) -> dict | None:
        if not isinstance(raw, dict) or not raw.get("kind") or not raw.get("block_id"):
            return None
        return {key: value for key, value in raw.items() if value is not None}

    @staticmethod
    def _prompt(document: Document, command: str) -> str:
        lines = [f'The researcher asked: "{command}"', "", "The paper's blocks:"]

        budget = MAX_BLOCKS_OFFERED
        for section in document.sections:
            if budget <= 0:
                break
            lines.append(f"\n## {section.title}")
            for block in section.blocks:
                if budget <= 0:
                    break
                budget -= 1
                preview = " ".join(block.display_text.split())[:160]
                citations = len(block.cite_nodes)
                lines.append(
                    f"- {block.id} [{block.kind}, {citations} citation(s)] {preview}"
                )

        return "\n".join(lines)


# Notes
#
# The planner selects targets. It does not write a single word that reaches the
# paper. Its entire output is a small typed object, so a model that returns
# nonsense produces a validation error rather than a damaged manuscript, and
# there is no free-text field here that is later executed. `instruction` is
# passed to the writer as guidance and is never applied to the document itself.
#
# Splitting planning from writing is what keeps this off the "one giant prompt"
# path the brief warns about. This call sees the whole paper in outline and no
# prose worth rewriting; the writer sees one paragraph and knows nothing about
# the plan. Neither is in a position to do the other's damage.
#
# Blocks are offered as id, kind, citation count and a short preview rather
# than full text. The planner is choosing where to work, and full prose would
# cost tokens on every block in the paper to answer a question about which
# handful of them matter.
#
# Operations naming a block that does not exist are dropped here rather than
# failing the request. A model inventing "b_99" is a plan that cannot be run,
# not a reason to lose the operations it got right, and the user sees what was
# actually attempted.
#
# The schema pins `kind` to an enum matching the operation union in
# domain/edit.py. That is what makes an unknown operation kind unreachable
# rather than merely unlikely: with constrained decoding the model cannot emit
# one, and without it validation refuses it.
#
# PLAN_MAX_TOKENS is raised above the default because this is the largest
# prompt in the codebase and the model is a reasoning one. On gpt-oss the
# reasoning tokens are drawn from the same completion budget as the answer, so
# an outline of a hundred blocks produced enough reasoning to exhaust 2048
# before a single character of JSON was emitted. The response came back well
# formed and completely empty, which surfaced as "could not reach the model"
# when the model had in fact answered. Settings also pin reasoning_effort low,
# which cut the tokens spent thinking about a plan by roughly two thirds.
#
# MAX_OPERATIONS caps how much one command may change. "Rewrite my paper" is a
# request this tool should decline to satisfy in a single unreviewable step,
# and a bounded plan is also a bounded number of writer calls against a free
# tier rate limit.
