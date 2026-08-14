import asyncio

import httpx

from app.core.exceptions import ParserUnavailableError

FULLTEXT_ENDPOINT = "/api/processFulltextDocument"
ALIVE_ENDPOINT = "/api/isalive"

COORDINATE_ELEMENTS = ["ref", "biblStruct", "head", "p", "formula", "figure", "persName"]


class GrobidProvider:
    name = "grobid"

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 120.0,
        max_attempts: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    async def parse(self, pdf_bytes: bytes, filename: str) -> str:
        files = {"input": (filename, pdf_bytes, "application/pdf")}
        data = {
            "consolidateHeader": "0",
            "consolidateCitations": "0",
            "includeRawCitations": "1",
            "segmentSentences": "0",
            "teiCoordinates": COORDINATE_ELEMENTS,
        }

        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(
                        f"{self._base_url}{FULLTEXT_ENDPOINT}",
                        files=files,
                        data=data,
                    )
            except httpx.TimeoutException as exc:
                last_error = exc
                raise ParserUnavailableError(
                    f"The parser did not respond within {self._timeout_seconds:.0f}s."
                ) from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    break
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            if response.status_code == 204:
                raise ParserUnavailableError(
                    "The parser returned no content for this PDF. "
                    "It may be a scanned document with no text layer."
                )

            if response.status_code in (429, 503):
                if attempt == self._max_attempts:
                    raise ParserUnavailableError(
                        "The parser is busy and refused the request. Try again shortly."
                    )
                await asyncio.sleep(2 ** (attempt - 1))
                continue

            if response.status_code >= 400:
                raise ParserUnavailableError(
                    f"The parser rejected the request with status {response.status_code}."
                )

            body = response.text
            if not self._looks_like_tei(body):
                if attempt == self._max_attempts:
                    raise ParserUnavailableError(
                        "The parser endpoint answered with something other than TEI XML. "
                        "The service is most likely still starting up."
                    )
                await asyncio.sleep(2**attempt)
                continue

            return body

        raise ParserUnavailableError(
            f"Could not reach the parser at {self._base_url}: {last_error}"
        )

    async def is_alive(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(f"{self._base_url}{ALIVE_ENDPOINT}")
        except httpx.HTTPError:
            return False

        if response.status_code != 200:
            return False
        return response.text.strip().lower().startswith("true")

    @staticmethod
    def _looks_like_tei(body: str) -> bool:
        head = body.lstrip()[:400].lower()
        return "<tei" in head
