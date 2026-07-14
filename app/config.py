import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Database ──
    # Plain postgres:// URL; SQLAlchemy and procrastinate derive their own forms.
    database_url: str = "postgresql://prodocs:prodocs@localhost:5432/prodocs"

    # ── Auth (Supabase JWT, HS256) ──
    supabase_jwt_secret: str = "dev-secret-change-me"
    jwt_audience: str = "authenticated"
    # Supabase project for login/register proxying. Unset -> local dev tokens.
    supabase_url: str | None = None
    supabase_anon_key: str | None = None

    # ── LLM ──
    # Loaded from .env and exported to the process env so the OpenAI SDK and
    # pydantic-ai find it regardless of how the server was started.
    openai_api_key: str | None = None
    # pydantic-ai model strings, e.g. "openai:gpt-4.1-mini" or "azure:<deployment-name>".
    extract_model: str = "openai:gpt-4.1-mini"
    chat_model: str = "openai:gpt-4.1"
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-10-21"

    # ── Embeddings ──
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # ── Storage (Cloudflare R2 / any S3). Unset endpoint -> local disk under .data/blobs ──
    s3_endpoint_url: str | None = None
    s3_bucket: str = "prodocs"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    local_blob_dir: str = ".data/blobs"

    # ── API ──
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── Ingestion ──
    # Run the job worker inside the API process. Perfect for dev/small deployments
    # (one process to start); set EMBEDDED_WORKER=false to scale workers separately.
    embedded_worker: bool = True
    extract_max_chars: int = 24_000
    chunk_target_chars: int = 1_400
    chunk_overlap_chars: int = 200

    @property
    def sqlalchemy_url(self) -> str:
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    return settings
