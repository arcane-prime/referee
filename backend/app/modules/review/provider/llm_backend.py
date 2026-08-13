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


# Notes
#
# One method, and it always returns JSON matching a schema the caller supplies.
# There is no free-text completion here on purpose: every LLM call in review
# produces structured data that code then validates, so a backend that could
# return prose would invite somebody to parse it.
#
# The schema travels with the request rather than living in the backend,
# because the schema is the safety mechanism. Pass C's schema requires a quote
# field alongside the grade, which is what stops a model asserting a verdict
# with nothing behind it. Providers that support constrained decoding make that
# structurally impossible rather than merely requested.
#
# Keeping this narrow is what lets the whole stage run offline. A stub
# implementing this protocol returns canned answers, so the three passes, the
# quote verification and the finding assembly can all be developed and tested
# with no key and no network, exactly as the search backends allowed for
# stage 2.
