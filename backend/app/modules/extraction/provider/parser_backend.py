from typing import Protocol, runtime_checkable


@runtime_checkable
class ParserBackend(Protocol):
    name: str

    async def parse(self, pdf_bytes: bytes, filename: str) -> str:
        ...

    async def is_alive(self) -> bool:
        ...
