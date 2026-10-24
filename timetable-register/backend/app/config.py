import os
from functools import lru_cache

LOCAL_DEFAULT = "postgresql+psycopg://timetable:timetable@localhost:5432/timetable"


def _database_url() -> str:
    """DATABASE_URL (or the POSTGRES_URL that Vercel/Neon injects), normalised for psycopg 3.

    On Vercel without a database attached, fall back to an ephemeral SQLite file in /tmp
    so the demo still works (data resets whenever the function instance is recycled).
    """
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ""
    if not url:
        return "sqlite:////tmp/timetable.db" if os.getenv("VERCEL") else LOCAL_DEFAULT
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings:
    """Runtime settings, read from environment variables."""

    def __init__(self) -> None:
        self.database_url: str = _database_url()
        self.is_serverless: bool = bool(os.getenv("VERCEL"))
        self.secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production-please-0123456789")
        self.token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", str(12 * 60)))
        self.cors_origins: list[str] = [
            o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
        ]
        # e.g. https://timetable-register(-[a-z0-9-]+)?\.vercel\.app for preview deployments
        self.cors_origin_regex: str | None = os.getenv("CORS_ORIGIN_REGEX") or None
        self.frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
        self.auto_create_tables: bool = os.getenv("AUTO_CREATE_TABLES", "true").lower() == "true"
        self.seed_demo: bool = os.getenv("SEED_DEMO", "false").lower() == "true"
        self.default_time_limit: float = float(os.getenv("SCHEDULER_TIME_LIMIT", "15"))
        self.max_time_limit: float = float(os.getenv("SCHEDULER_MAX_TIME_LIMIT", "120"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
