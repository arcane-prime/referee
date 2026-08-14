from functools import lru_cache

from app.core.config import get_settings
from app.core.dependencies import get_http_cache
from app.modules.resolution.api.dependencies import get_search_backend
from app.modules.review.provider.cerebras_provider import CerebrasProvider
from app.modules.review.provider.claim_provider import ClaimProvider
from app.modules.review.provider.discovery_provider import DiscoveryProvider
from app.modules.review.provider.llm_backend import LlmBackend
from app.modules.review.provider.review_provider import ReviewProvider
from app.modules.review.provider.sentence_provider import SentenceProvider
from app.modules.review.provider.stub_llm_provider import StubLlmProvider
from app.modules.review.provider.support_provider import SupportProvider


@lru_cache
def get_llm_backend() -> LlmBackend:
    settings = get_settings()

    if not settings.cerebras_api_key:
        return StubLlmProvider()

    return CerebrasProvider(
        base_url=settings.cerebras_url,
        api_key=settings.cerebras_api_key,
        model=settings.review_model,
        timeout_seconds=settings.review_timeout_seconds,
        cache=get_http_cache(),
        reasoning_effort=settings.reasoning_effort,
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


# Notes
#
# With no API key configured the stub backend is wired in rather than the app
# refusing to start. Every route stays reachable, review returns an empty but
# well formed result, and the whole stage can be developed and demonstrated
# offline. The model name in the response says "stub", so nobody can mistake an
# offline run for a real one.
#
# get_llm_backend is typed as the protocol, so which model provider is used
# stays a wiring decision. Swapping Cerebras for another provider is one new
# file and a settings change; nothing in the three passes moves.
