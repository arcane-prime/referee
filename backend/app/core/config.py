from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Referee API"
    api_prefix: str = ""

    data_dir: Path = Path("data")
    max_upload_bytes: int = 50 * 1024 * 1024

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]

    grobid_url: str = "https://kermitt2-grobid.hf.space"
    grobid_timeout_seconds: float = 180.0

    openalex_url: str = "https://api.openalex.org"
    openalex_mailto: str = ""

    semantic_scholar_url: str = "https://api.semanticscholar.org"
    semantic_scholar_api_key: str = ""

    search_timeout_seconds: float = 20.0
    resolution_concurrency: int = 3
    search_fallback_enabled: bool = True
    verification_budget_seconds: float = 75.0

    cerebras_url: str = "https://api.cerebras.ai"
    cerebras_api_key: str = ""
    review_model: str = "gpt-oss-120b"
    review_timeout_seconds: float = 90.0
    review_concurrency: int = 4

    http_cache_enabled: bool = True
    http_cache_ttl_hours: float = 720.0

    @property
    def http_cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def papers_dir(self) -> Path:
        return self.data_dir / "papers"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Notes
#
# Settings are read once and cached, so every provider sees the same values and
# tests can override them by clearing the cache.
#
# `grobid_url` defaults to the public hosted GROBID so extraction works with no
# local infrastructure. That instance is shared and rate limited, so it is a
# development convenience rather than a deployment target. Pointing at a local
# container is a one-line change: GROBID_URL=http://localhost:8070 in .env, and
# no code is touched.
#
# `data_dir` is relative by default, which resolves against the process working
# directory. Run uvicorn from the backend/ folder, or set DATA_DIR to an
# absolute path in .env.
#
# The CORS list covers 3000 and 3001 because Next silently moves to the next
# free port when 3000 is occupied. A missing origin surfaces in the browser as
# a CORS failure that gives no hint the real cause was a port change.
#
# `openalex_mailto` is optional but worth setting. Sending it opts into
# OpenAlex's polite pool, which is faster and more reliable, and it is the
# courteous way to use a free public service at forty requests a paper.
#
# `semantic_scholar_api_key` is optional too. Without it the client shares a
# small anonymous rate limit, which is tolerable because Semantic Scholar is
# only asked for abstracts OpenAlex could not supply.
#
# `resolution_concurrency` bounds how many references are looked up at once.
# Forty sequential lookups is a long spinner; forty simultaneous ones is how a
# client earns a rate limit.
