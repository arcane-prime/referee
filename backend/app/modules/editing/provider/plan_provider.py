from pydantic import TypeAdapter, ValidationError

from app.domain.document import Document
from app.domain.edit import EditOperation, EditPlan
from app.modules.review.provider.llm_backend import LlmBackend

OPERATION_ADAPTER = TypeAdapter(EditOperation)

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
    "required": ["intent", "scope", "note", "operations"],
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
                "required": [
                    "kind",
                    "block_id",
                    "target_ratio",
                    "instruction",
                    "ref_id",
                ],
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

        valid = []
        dropped = 0
        for raw in operations[:MAX_OPERATIONS]:
            try:
                valid.append(OPERATION_ADAPTER.validate_python(raw))
            except ValidationError:
                dropped += 1

        return EditPlan(
            command=command,
            intent=payload.get("intent") or command,
            scope=payload.get("scope"),
            note=self._note(payload.get("note"), valid, dropped),
            operations=valid,
        )

    @staticmethod
    def _note(note: str | None, valid: list, dropped: int) -> str | None:
        if dropped and not valid:
            return (
                f"The plan named {dropped} change(s) this tool cannot carry out, "
                f"so nothing was proposed. Adding a citation needs a reference "
                f"that was already found in a database."
            )
        if dropped:
            return f"{dropped} proposed change(s) were not valid and were skipped."
        return note

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
