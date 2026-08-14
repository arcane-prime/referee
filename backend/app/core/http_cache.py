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
