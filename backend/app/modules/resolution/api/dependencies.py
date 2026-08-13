from functools import lru_cache

from app.core.config import get_settings
from app.core.dependencies import get_http_cache
from app.modules.resolution.provider.fallback_search_provider import (
    FallbackSearchProvider,
)
from app.modules.resolution.provider.matcher_provider import MatcherProvider
from app.modules.resolution.provider.openalex_provider import OpenAlexProvider
from app.modules.resolution.provider.resolution_provider import ResolutionProvider
from app.modules.resolution.provider.search_backend import AbstractBackend, SearchBackend
from app.modules.resolution.provider.semantic_scholar_provider import (
    SemanticScholarProvider,
)


@lru_cache
def get_semantic_scholar_provider() -> SemanticScholarProvider:
    settings = get_settings()
    return SemanticScholarProvider(
        base_url=settings.semantic_scholar_url,
        api_key=settings.semantic_scholar_api_key or None,
        timeout_seconds=settings.search_timeout_seconds,
        cache=get_http_cache(),
    )


@lru_cache
def get_search_backend() -> SearchBackend:
    settings = get_settings()
    openalex = OpenAlexProvider(
        base_url=settings.openalex_url,
        mailto=settings.openalex_mailto,
        timeout_seconds=settings.search_timeout_seconds,
        cache=get_http_cache(),
    )

    if not settings.search_fallback_enabled:
        return openalex

    return FallbackSearchProvider(
        primary=openalex,
        standby=get_semantic_scholar_provider(),
    )


@lru_cache
def get_abstract_backend() -> AbstractBackend:
    return get_semantic_scholar_provider()


@lru_cache
def get_resolution_provider() -> ResolutionProvider:
    return ResolutionProvider(
        search=get_search_backend(),
        matcher=MatcherProvider(),
        abstracts=get_abstract_backend(),
        concurrency=get_settings().resolution_concurrency,
    )


# Notes
#
# Both backends are annotated as their protocols rather than their concrete
# classes, so which database is primary and which supplies abstracts stays a
# wiring decision made here rather than a dependency baked into the
# orchestrator.
