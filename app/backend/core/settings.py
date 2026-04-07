import os
from dataclasses import dataclass
from functools import lru_cache


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return default
    return [p.strip() for p in raw.split(",") if p.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "BILBO API")
    environment: str = os.getenv("APP_ENV", "development")

    database_url: str = os.getenv("DATABASE_URL", "")
    postgres_host: str = os.getenv("POSTGRES_HOST", "db")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "bioinfo")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")

    secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

    cors_origins: list[str] = None  # type: ignore[assignment]
    cors_allow_credentials: bool = _bool("CORS_ALLOW_CREDENTIALS", True)

    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    celery_result_backend: str = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

    llm_primary_model: str = os.getenv("LLM_PRIMARY_MODEL", "qwen3:14b")
    llm_fallback_models: list[str] = None  # type: ignore[assignment]

    users_root: str = os.getenv("USERS_ROOT", "/users")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    artifact_retention_days: int = int(os.getenv("ARTIFACT_RETENTION_DAYS", "30"))
    log_retention_days: int = int(os.getenv("LOG_RETENTION_DAYS", "30"))
    audit_retention_days: int = int(os.getenv("AUDIT_RETENTION_DAYS", "90"))
    db_startup_max_attempts: int = int(os.getenv("DB_STARTUP_MAX_ATTEMPTS", "30"))
    db_startup_retry_seconds: float = float(os.getenv("DB_STARTUP_RETRY_SECONDS", "2"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "cors_origins", _list("CORS_ORIGINS", ["http://localhost:8000", "http://127.0.0.1:8000", "null"]))
        object.__setattr__(self, "llm_fallback_models", _list("LLM_FALLBACK_MODELS", ["qwen3:8b", "qwen3:0.6b"]))

        db_url = (self.database_url or "").strip()
        if db_url:
            object.__setattr__(self, "database_url", db_url)
        else:
            if not self.postgres_password:
                raise RuntimeError(
                    "POSTGRES_PASSWORD is required when DATABASE_URL is not set. "
                    "Set POSTGRES_PASSWORD in .env or provide a full DATABASE_URL."
                )
            built_url = (
                f"postgresql://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
            object.__setattr__(self, "database_url", built_url)

        if self.environment.lower() in {"prod", "production"}:
            if self.secret_key == "change-me-in-production":
                raise RuntimeError("SECRET_KEY must be configured in production.")
            if not self.database_url:
                raise RuntimeError("DATABASE_URL (or POSTGRES_* vars) must be configured in production.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
