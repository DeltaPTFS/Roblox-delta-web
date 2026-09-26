from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    """Force PostgreSQL URLs to use the installed psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return url.replace(prefix, "postgresql+psycopg://", 1)
    return url


settings = get_settings()
url = normalize_database_url(settings.database_url)
if settings.is_serverless and url.startswith("sqlite"):
    raise RuntimeError("DATABASE_URL must use PostgreSQL in serverless production; SQLite is not supported")
engine = create_engine(url, pool_pre_ping=True, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
