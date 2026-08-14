from typing import Protocol, runtime_checkable


@runtime_checkable
class LlmBackend(Protocol):
    name: str

    async def complete_json(
        self,
        system: str,
        user: str,
        schema: dict,
        schema_name: str,
        max_tokens: int = 2048,
    ) -> dict:
        ...
