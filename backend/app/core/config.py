from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Meeting AI API"
    app_env: str = "dev"

    database_url: str = "sqlite:///./app.db"
    redis_url: str = "redis://localhost:6379/0"
    task_always_eager: bool = True

    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "recordings"
    s3_region: str = "us-east-1"
    local_storage_dir: str = ".local_s3"

    openai_api_key: str | None = None
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    openai_chat_model: str = "gpt-4.1-mini"
    openai_embed_model: str = "text-embedding-3-small"
    openai_timeout_sec: float = 60.0

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24 * 7
    enable_dev_auth_routes: bool = True

    embedding_dim: int = 1536
    rag_top_k: int = 4
    chunk_max_chars: int = 800
    chunk_overlap_chars: int = 120
    qa_max_context_chars: int = 2800
    qa_history_turns: int = 3
    qa_history_chars_per_turn: int = 280
    summary_map_chunk_chars: int = 1800
    summary_map_max_chunks: int = 12

    cors_origins: str = "*"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def s3_enabled(self) -> bool:
        return bool(
            self.s3_endpoint_url and self.s3_access_key and self.s3_secret_key
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
