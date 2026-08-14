class StubLlmProvider:
    name = "stub"

    def __init__(self, answers: dict[str, dict] | None = None) -> None:
        self._answers = answers or {}
        self.calls: list[tuple[str, str]] = []

    async def complete_json(
        self,
        system: str,
        user: str,
        schema: dict,
        schema_name: str,
        max_tokens: int = 2048,
    ) -> dict:
        self.calls.append((schema_name, user))

        if schema_name in self._answers:
            return self._answers[schema_name]

        return self._empty_for(schema)

    @staticmethod
    def _empty_for(schema: dict) -> dict:
        empty: dict = {}
        for key, definition in (schema.get("properties") or {}).items():
            kind = definition.get("type")
            if kind == "array":
                empty[key] = []
            elif kind == "string":
                empty[key] = ""
            elif kind in ("integer", "number"):
                empty[key] = 0
            elif kind == "boolean":
                empty[key] = False
            else:
                empty[key] = None
        return empty
