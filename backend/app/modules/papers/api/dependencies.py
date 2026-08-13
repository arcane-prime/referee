from functools import lru_cache

from app.core.config import get_settings
from app.core.dependencies import get_storage_provider
from app.modules.papers.provider.paper_provider import PaperProvider


@lru_cache
def get_paper_provider() -> PaperProvider:
    return PaperProvider(
        storage=get_storage_provider(),
        max_upload_bytes=get_settings().max_upload_bytes,
    )


# Notes
#
# Wiring lives in the api layer so that providers never construct their own
# collaborators. A provider receives what it needs through its constructor,
# which is what lets a test hand it a temporary directory instead of the real
# data folder.
#
# Tests replace this with app.dependency_overrides[get_paper_provider] rather
# than clearing the cache.
