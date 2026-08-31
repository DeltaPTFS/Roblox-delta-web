from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    """Force PostgreSQL URLs to use the installed psycopg 3 driver."""
    for prefix in (
        "postgres://",
        "postgresql://",
        "postgresql+psycopg2://",
    ):
        if url.startswith(prefix):
            return url.replace(prefix, "postgresql+psycopg://", 1)
    return url


url = normalize_database_url(get_settings().database_url)

engine = create_engine(
    url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False}
    if url.startswith("sqlite")
    else {},
)

SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db():
    with SessionLocal() as db:
        yield db
