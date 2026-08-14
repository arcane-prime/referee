from functools import lru_cache

from app.core.config import get_settings
from app.core.http_cache import HttpCache
from app.core.library_provider import LibraryProvider
from app.core.storage_provider import StorageProvider


@lru_cache
def get_storage_provider() -> StorageProvider:
    return StorageProvider(papers_dir=get_settings().papers_dir)


@lru_cache
def get_library_provider() -> LibraryProvider:
    return LibraryProvider(storage=get_storage_provider())


@lru_cache
def get_http_cache() -> HttpCache:
    settings = get_settings()
    return HttpCache(
        root=settings.http_cache_dir,
        ttl_seconds=settings.http_cache_ttl_hours * 3600,
        enabled=settings.http_cache_enabled,
    )


# Notes
#
# Storage is shared infrastructure, so it is constructed once here rather than
# rebuilt inside each module's wiring. Two modules building their own instance
# would work, but the on-disk layout would then be defined in two places.
#
# The cache takes no arguments because Settings is a Pydantic model and so not
# hashable. get_settings() is already cached, so resolving it inside yields the
# same single instance.
