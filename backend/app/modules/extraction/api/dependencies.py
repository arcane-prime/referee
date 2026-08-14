from functools import lru_cache

from app.core.config import get_settings
from app.core.dependencies import get_storage_provider
from app.modules.extraction.provider.extraction_provider import ExtractionProvider
from app.modules.extraction.provider.grobid_provider import GrobidProvider
from app.modules.extraction.provider.parser_backend import ParserBackend
from app.modules.extraction.provider.reference_provider import ReferenceProvider
from app.modules.extraction.provider.style_provider import StyleProvider
from app.modules.extraction.provider.tei_provider import TeiProvider


@lru_cache
def get_parser_backend() -> ParserBackend:
    settings = get_settings()
    return GrobidProvider(
        base_url=settings.grobid_url,
        timeout_seconds=settings.grobid_timeout_seconds,
    )


@lru_cache
def get_extraction_provider() -> ExtractionProvider:
    return ExtractionProvider(
        storage=get_storage_provider(),
        parser=get_parser_backend(),
        tei_provider=TeiProvider(reference_provider=ReferenceProvider()),
        style_provider=StyleProvider(),
    )
