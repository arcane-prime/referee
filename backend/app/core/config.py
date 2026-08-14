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

    openai_url: str = "https://api.openai.com"
    openai_api_key: str = ""
    review_model: str = "gpt-4.1-mini"
    review_timeout_seconds: float = 90.0
    review_concurrency: int = 12

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
