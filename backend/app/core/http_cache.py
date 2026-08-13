import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlencode

VOLATILE_PARAMS = frozenset({"mailto", "api_key", "email"})


def request_key(url: str, params: dict[str, str] | None = None) -> str:
    stable = sorted(
        (key, value)
        for key, value in (params or {}).items()
        if key not in VOLATILE_PARAMS
    )
    canonical = f"{url}?{urlencode(stable)}" if stable else url
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class HttpCache:
    def __init__(self, root: Path, ttl_seconds: float, enabled: bool = True) -> None:
        self._root = root
        self._ttl_seconds = ttl_seconds
        self._enabled = enabled
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def get(self, namespace: str, key: str) -> dict | None:
        if not self._enabled:
            return None

        path = self._path(namespace, key)
        if not path.is_file():
            self.misses += 1
            return None

        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.misses += 1
            return None

        if time.time() - entry.get("fetched_at", 0) > self._ttl_seconds:
            self.misses += 1
            return None

        self.hits += 1
        return entry

    def put(self, namespace: str, key: str, payload: dict | None) -> None:
        if not self._enabled:
            return

        path = self._path(namespace, key)
        entry = {"fetched_at": time.time(), "payload": payload}

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(entry), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            return

    def _path(self, namespace: str, key: str) -> Path:
        return self._root / namespace / key[:2] / f"{key}.json"


# Notes
#
# The design brief calls a keyed disk cache "not optional" for stage 2, and the
# reason turned out to be sharper than politeness. OpenAlex meters a daily
# budget, not just a rate: a thousand requests a day, and one paper costs forty
# to eighty. Without a cache, a dozen debugging runs exhausts the day and
# development stops until midnight UTC. Sending a mailto does not exempt you.
#
# So the cache is not a performance tweak, it is what makes the stage
# developable at all. Bibliographic records are close to immutable, so the same
# query returns the same answer effectively forever, and paying for it twice is
# pure waste.
#
# The key is a hash of the canonical URL with query parameters sorted, so
# parameter order never produces two entries for one request. Credential-ish
# and identity parameters are excluded: mailto identifies the caller and has no
# effect on the answer, and keying on it would throw away the whole cache the
# day someone sets their own address.
#
# Misses are stored too. `payload: null` records "this was asked and there was
# nothing there", which matters because unresolvable references are exactly the
# ones a developer re-runs most while tuning thresholds, and they would
# otherwise cost quota on every attempt.
#
# Writes go to a temporary file and are then renamed, since rename is atomic on
# every platform we care about. References resolve concurrently, so a half
# written entry is a real possibility, and a truncated JSON file that parses as
# a miss would be silently wrong rather than loudly broken.
#
# Every failure path degrades to a miss rather than raising. A cache that
# cannot be read or written should slow the system down, never break it.
