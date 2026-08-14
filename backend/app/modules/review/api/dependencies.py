from functools import lru_cache

from app.core.config import get_settings
from app.core.dependencies import get_http_cache
from app.modules.resolution.api.dependencies import get_search_backend
from app.modules.review.provider.claim_provider import ClaimProvider
from app.modules.review.provider.discovery_provider import DiscoveryProvider
from app.modules.review.provider.llm_backend import LlmBackend
from app.modules.review.provider.openai_provider import OpenAiProvider
from app.modules.review.provider.review_provider import ReviewProvider
from app.modules.review.provider.sentence_provider import SentenceProvider
from app.modules.review.provider.stub_llm_provider import StubLlmProvider
from app.modules.review.provider.support_provider import SupportProvider


@lru_cache
def get_llm_backend() -> LlmBackend:
    settings = get_settings()

    if not settings.openai_api_key:
        return StubLlmProvider()

    return OpenAiProvider(
        base_url=settings.openai_url,
        api_key=settings.openai_api_key,
        model=settings.review_model,
        timeout_seconds=settings.review_timeout_seconds,
        cache=get_http_cache(),
    )


@lru_cache
def get_review_provider() -> ReviewProvider:
    llm = get_llm_backend()

    return ReviewProvider(
        sentences=SentenceProvider(),
        claims=ClaimProvider(llm=llm),
        support=SupportProvider(llm=llm),
        discovery=DiscoveryProvider(llm=llm, search=get_search_backend()),
        concurrency=get_settings().review_concurrency,
    )
