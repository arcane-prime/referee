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
