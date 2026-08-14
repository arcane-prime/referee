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
