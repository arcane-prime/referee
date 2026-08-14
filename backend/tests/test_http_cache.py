import time

import pytest

from app.core.http_cache import HttpCache, request_key


@pytest.fixture
def cache(tmp_path):
    return HttpCache(root=tmp_path, ttl_seconds=3600)


class TestRequestKey:
    def test_parameter_order_does_not_change_the_key(self):
        a = request_key("https://api.openalex.org/works", {"filter": "x", "per-page": "5"})
        b = request_key("https://api.openalex.org/works", {"per-page": "5", "filter": "x"})

        assert a == b

    def test_identity_parameters_are_excluded_from_the_key(self):
        without = request_key("https://api.openalex.org/works", {"filter": "x"})
        with_mailto = request_key(
            "https://api.openalex.org/works",
            {"filter": "x", "mailto": "someone@example.com"},
        )

        assert without == with_mailto

    def test_different_queries_produce_different_keys(self):
        a = request_key("https://api.openalex.org/works", {"filter": "title.search:one"})
        b = request_key("https://api.openalex.org/works", {"filter": "title.search:two"})

        assert a != b


class TestCacheBehaviour:
    def test_a_stored_payload_comes_back(self, cache):
        cache.put("openalex", "abc", {"results": [1, 2, 3]})

        assert cache.get("openalex", "abc")["payload"] == {"results": [1, 2, 3]}

    def test_a_miss_returns_none(self, cache):
        assert cache.get("openalex", "never-stored") is None

    def test_namespaces_do_not_collide(self, cache):
        cache.put("openalex", "same-key", {"source": "openalex"})
        cache.put("semantic_scholar", "same-key", {"source": "s2"})

        assert cache.get("openalex", "same-key")["payload"]["source"] == "openalex"
        assert cache.get("semantic_scholar", "same-key")["payload"]["source"] == "s2"

    def test_a_negative_result_is_cached_too(self, cache):
        cache.put("openalex", "nothing-there", None)
        entry = cache.get("openalex", "nothing-there")

        assert entry is not None
        assert entry["payload"] is None

    def test_expired_entries_are_treated_as_misses(self, tmp_path):
        expiring = HttpCache(root=tmp_path, ttl_seconds=0.05)
        expiring.put("openalex", "abc", {"results": []})
        time.sleep(0.1)

        assert expiring.get("openalex", "abc") is None

    def test_a_disabled_cache_stores_and_returns_nothing(self, tmp_path):
        disabled = HttpCache(root=tmp_path, ttl_seconds=3600, enabled=False)
        disabled.put("openalex", "abc", {"results": []})

        assert disabled.get("openalex", "abc") is None

    def test_corrupt_entries_degrade_to_a_miss(self, cache, tmp_path):
        cache.put("openalex", "abc", {"results": []})
        path = next(tmp_path.rglob("abc.json"))
        path.write_text("{ this is not json", encoding="utf-8")

        assert cache.get("openalex", "abc") is None

    def test_hits_and_misses_are_counted(self, cache):
        cache.put("openalex", "abc", {"results": []})
        cache.get("openalex", "abc")
        cache.get("openalex", "missing")

        assert (cache.hits, cache.misses) == (1, 1)
