from typing import Protocol, runtime_checkable


@runtime_checkable
class ParserBackend(Protocol):
    name: str

    async def parse(self, pdf_bytes: bytes, filename: str) -> str:
        ...

    async def is_alive(self) -> bool:
        ...


# Notes
#
# The contract is deliberately narrow: PDF bytes in, raw TEI XML out. A backend
# knows nothing about Document, CiteNode or any other domain type, and the TEI
# parser knows nothing about HTTP.
#
# That single seam is what makes the rest of extraction testable. GROBID output
# can be captured once, committed as a fixture, and replayed forever, so the
# parser test suite runs in under a second with no container and no network.
#
# It is also the honest answer to "why a Java container instead of parsing the
# PDF ourselves". Parsing is a pluggable stage; GROBID is the production
# implementation; anything else that can return TEI for a PDF satisfies this
# Protocol and drops in without touching a line downstream.
