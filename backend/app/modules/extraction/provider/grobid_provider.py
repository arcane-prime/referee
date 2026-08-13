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


# Notes
#
# This provider does one thing: hand a PDF to GROBID and return the TEI string.
# It never imports a domain model, which is what keeps the TEI parser testable
# against a committed fixture with no container running.
#
# consolidateCitations=0 stops GROBID from calling external services to enrich
# references. That lookup is stage 2's job, done deliberately against OpenAlex
# with scoring we control, rather than as an opaque side effect of parsing.
#
# includeRawCitations=1 is the flag that matters most. It makes GROBID return
# the verbatim reference string alongside its parsed fields, so a reference
# whose field parsing failed completely is still recoverable: it can be shown
# to the user as printed and sent to a search API as one query string. Without
# it, a failed parse is a lost reference.
#
# teiCoordinates asks for element geometry. It can only be requested while the
# PDF is being read, so leaving it out now would mean re-parsing every paper
# later to point at anything inside the original file.
#
# It is sent as one repeated form field per element name, not as a single
# comma-joined value. GROBID reads it as a list, and a comma-joined string is
# accepted and then silently ignored, so the request succeeds and the output
# simply carries no coordinates. That failure is invisible without checking the
# TEI, which is how the first real run produced zero of them.
#
# The repetition is expressed as a list *value* inside the data dict. httpx
# treats a list passed as `data` itself as raw streaming content rather than as
# form fields, which fails at send time with a confusing complaint about sync
# streams on an async client.
#
# Retries cover transport failures and the busy responses (429, 503) that a
# shared public instance returns under load. A timeout is not retried: the
# request already consumed the full budget, and a second attempt would double a
# wait the user is sitting through.
#
# HTTP 204 from GROBID means it parsed the file and found nothing, which in
# practice means a scanned PDF with no text layer. That is reported as such
# rather than as an empty but successful extraction.
#
# A 200 is not sufficient evidence of success. The hosted instance sits behind
# a platform wrapper that answers 200 with an HTML "starting up" page while the
# service is cold, and handing that to an XML parser produces a confusing
# downstream failure that points at the document instead of the service. So the
# body is checked for a TEI root before being trusted, and a non-TEI answer is
# retried as the transient condition it usually is.
#
# is_alive checks the body for the same reason: GROBID answers its liveness
# endpoint with the literal string "true", and a 200 alone would report a
# sleeping service as healthy.
