class IdMinter:
    def __init__(self, start: int = 0) -> None:
        self._seq = start

    def mint(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}_{self._seq:04d}"

    @property
    def seq(self) -> int:
        return self._seq
