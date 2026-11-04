"""Database engine, session factory and template environment."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import BASE_DIR, settings

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _normalize_url(url: str) -> str:
    """Make a relative SQLite path independent of the current working directory."""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url
    raw = url[len(prefix):]
    if not raw or raw == ":memory:" or Path(raw).is_absolute():
        return url
    return prefix + (BASE_DIR / raw).resolve().as_posix()


def _create_engine(url: str):
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


DATABASE_URL = _normalize_url(settings.DATABASE_URL)
engine = _create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_paragraphs_book_para "
    "ON paragraphs (book_id, para_index)",
    "CREATE INDEX IF NOT EXISTS ix_comments_paragraph_status "
    "ON comments (paragraph_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_comments_book ON comments (book_id)",
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(engine)
    # create_all() does not add indexes to tables that already exist, and this
    # project ships with a pre-populated SQLite file, so create them explicitly.
    # Indexes are an optimisation: a read-only database must still be readable.
    if engine.dialect.name == "sqlite":
        try:
            with engine.begin() as conn:
                for statement in _INDEX_STATEMENTS:
                    conn.execute(text(statement))
        except SQLAlchemyError as exc:
            logger.warning("Could not create indexes (read-only database?): %s", exc)
