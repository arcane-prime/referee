import asyncio
import json

import httpx

from app.core.exceptions import ReviewUnavailableError
from app.core.http_cache import HttpCache, request_key

CHAT_PATH = "/v1/chat/completions"
RATE_LIMIT_BACKOFF_SECONDS = (2.0, 5.0, 10.0, 20.0)


class OpenAiProvider:
    name = "openai"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 90.0,
        max_attempts: int = 4,
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

        payload = self._parse(await self._post(body))

        if self._cache is not None:
            self._cache.put(self.name, cache_key, payload)

        return payload

    async def _post(self, body: dict) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    response = await client.post(
                        f"{self._base_url}{CHAT_PATH}", headers=headers, json=body
                    )
                except httpx.HTTPError as exc:
                    last_error = exc
                    if attempt == self._max_attempts:
                        break
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue

                if response.status_code in (429, 500, 502, 503, 529):
                    if attempt == self._max_attempts:
                        raise ReviewUnavailableError(
                            f"The review model is rate limiting or unavailable "
                            f"(status {response.status_code}). Try again shortly."
                        )
                    index = min(attempt - 1, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)
                    await asyncio.sleep(
                        self._retry_after(response) or RATE_LIMIT_BACKOFF_SECONDS[index]
                    )
                    continue

                if response.status_code == 401:
                    raise ReviewUnavailableError(
                        "The review model rejected the API key. Check OPENAI_API_KEY."
                    )

                if response.status_code >= 400:
                    raise ReviewUnavailableError(
                        f"The review model returned status {response.status_code}: "
                        f"{response.text[:300]}"
                    )

                try:
                    content = self._content_of(response.json())
                except (ValueError, KeyError, IndexError) as exc:
                    last_error = exc
                    if attempt == self._max_attempts:
                        break
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue

                if content:
                    return content

                last_error = ValueError("the model returned an empty message")
                if attempt == self._max_attempts:
                    break
                await asyncio.sleep(2 ** (attempt - 1))

        raise ReviewUnavailableError(f"Could not reach the review model: {last_error}")

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        raw = response.headers.get("retry-after")
        try:
            return min(float(raw), 30.0) if raw else None
        except ValueError:
            return None

    @staticmethod
    def _content_of(data: dict) -> str:
        choice = data["choices"][0]

        if choice.get("finish_reason") == "length":
            raise ReviewUnavailableError(
                "The review model hit its token limit before finishing its answer."
            )

        content = choice["message"].get("content")
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            return "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )

        return ""

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
