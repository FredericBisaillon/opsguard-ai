from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from opsguard_api.constants import (
    DEFAULT_ANSWER_CONTEXT_MAX_CHARS,
    DEFAULT_ANSWER_SOURCE_MAX_CHARS,
    DEFAULT_EMBEDDING_BATCH_SIZE,
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    DEFAULT_SEARCH_TOP_K,
    MAX_SEARCH_QUERY_CHARS,
    MAX_SEARCH_TOP_K,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    database_url: str
    upload_dir: Path = PROJECT_ROOT / "data" / "uploads"
    extracted_text_dir: Path = PROJECT_ROOT / "data" / "extracted"
    max_upload_size_mb: int = Field(default=10, gt=0)
    chunk_max_chars: int = Field(default=1200, gt=0)
    chunk_overlap_chars: int = Field(default=150, ge=0)
    ops_guard_api_key: SecretStr | None = None
    require_api_key: bool = True
    openai_api_key: str | None = None
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_dimensions: int = Field(default=DEFAULT_EMBEDDING_DIMENSIONS, gt=0)
    embedding_batch_size: int = Field(default=DEFAULT_EMBEDDING_BATCH_SIZE, gt=0)
    default_search_top_k: int = Field(default=DEFAULT_SEARCH_TOP_K, gt=0)
    max_search_top_k: int = Field(default=MAX_SEARCH_TOP_K, gt=0)
    max_search_query_chars: int = Field(default=MAX_SEARCH_QUERY_CHARS, gt=0)
    llm_model: str = DEFAULT_LLM_MODEL
    answer_context_max_chars: int = Field(
        default=DEFAULT_ANSWER_CONTEXT_MAX_CHARS,
        gt=0,
    )
    answer_source_max_chars: int = Field(
        default=DEFAULT_ANSWER_SOURCE_MAX_CHARS,
        gt=0,
    )
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
