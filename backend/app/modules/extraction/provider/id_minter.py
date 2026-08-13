class IdMinter:
    def __init__(self, start: int = 0) -> None:
        self._seq = start

    def mint(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}_{self._seq:04d}"

    @property
    def seq(self) -> int:
        return self._seq


# Notes
#
# One minter is threaded through an entire parse so that every node id is
# unique across the whole document, and its final value is stored on the
# Document as `seq`.
#
# That stored value is what lets a later edit mint ids that cannot collide with
# anything already in the paper. A counter that restarted per parse, or lived
# only in memory, would eventually hand out an id that already exists, and the
# diff and invariant checker both key on ids being unique.
