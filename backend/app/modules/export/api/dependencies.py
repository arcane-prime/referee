from functools import lru_cache

from app.core.dependencies import get_library_provider
from app.modules.editing.api.dependencies import get_revision_provider
from app.modules.export.provider.export_provider import ExportProvider


@lru_cache
def get_export_provider() -> ExportProvider:
    return ExportProvider(
        revisions=get_revision_provider(),
        library=get_library_provider(),
    )
