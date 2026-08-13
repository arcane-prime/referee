import asyncio
import json

import httpx

from app.core.exceptions import ReviewUnavailableError
from app.core.http_cache import HttpCache, request_key

CHAT_PATH = "/v1/chat/completions"
RATE_LIMIT_BACKOFF_SECONDS = (5.0, 15.0, 30.0, 45.0)


class CerebrasProvider:
    name = "cerebras"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 90.0,
        max_attempts: int = 5,
        temperature: float = 0.0,
        cache: HttpCache | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._temperature = temperature
        self._cache = cache

    async def complete_json(
        self,
        system: str,
        user: str,
        schema: dict,
        schema_name: str,
        max_tokens: int = 2048,
    ) -> dict:
        body = {
            "model": self._model,
            "temperature": self._temperature,
            "max_completion_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }

        cache_key = request_key(
            f"{self._base_url}{CHAT_PATH}",
            {"model": self._model, "body": json.dumps(body, sort_keys=True)},
        )

        if self._cache is not None:
            cached = self._cache.get(self.name, cache_key)
            if cached is not None and cached.get("payload") is not None:
                return cached["payload"]

        content = await self._post(body)
        payload = self._parse(content)

        if self._cache is not None:
            self._cache.put(self.name, cache_key, payload)

        return payload

    async def _post(self, body: dict) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(
                        f"{self._base_url}{CHAT_PATH}", json=body, headers=headers
                    )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    break
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            if response.status_code in (429, 503):
                if attempt == self._max_attempts:
                    raise ReviewUnavailableError(
                        "The review model is rate limiting this client. Try again shortly."
                    )
                index = min(attempt - 1, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)
                await asyncio.sleep(RATE_LIMIT_BACKOFF_SECONDS[index])
                continue

            if response.status_code == 401:
                raise ReviewUnavailableError(
                    "The review model rejected the API key. Check CEREBRAS_API_KEY."
                )

            if response.status_code >= 400:
                raise ReviewUnavailableError(
                    f"The review model returned status {response.status_code}: "
                    f"{response.text[:200]}"
                )

            try:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError) as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    break
                await asyncio.sleep(2 ** (attempt - 1))
                continue

        raise ReviewUnavailableError(f"Could not reach the review model: {last_error}")

    @staticmethod
    def _parse(content: str) -> dict:
        try:
            payload = json.loads(content)
        except ValueError as exc:
            raise ReviewUnavailableError(
                "The review model returned output that was not valid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise ReviewUnavailableError(
                "The review model returned JSON that was not an object."
            )
        return payload


# Notes
#
# Cerebras exposes an OpenAI-shaped chat endpoint with a json_schema response
# format. strict: true turns on constrained decoding, so the model cannot emit
# a token sequence that violates the schema. That is stronger than asking for
# JSON and hoping: the required quote field in the support schema becomes
# something the decoder is unable to leave out.
#
# temperature is zero because every call here is a judgement, not a piece of
# writing. Two runs over the same paper should produce the same findings, and
# sampling variety would only make review results irreproducible.
#
# Responses are cached on the exact request body, so re-running review over an
# unchanged paper costs nothing and returns the same findings. During
# development that turns a slow, quota-consuming loop into an instant one, and
# it is also what makes a screen recording repeatable.
#
# A 401 is separated from other failures because it has a specific fix. Losing
# an afternoon to a generic "model unavailable" when the real problem is an
# unset key is a bad trade for one branch.
#
# The response is validated as a JSON object here rather than trusted. Even
# with constrained decoding, a truncated response caused by hitting the token
# limit can arrive as unparseable text, and that must surface as an error
# rather than as an empty finding list that looks like a clean review.
