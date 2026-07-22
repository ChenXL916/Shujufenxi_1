from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _configure_sqlite_connection(dbapi_connection: Any, _: Any) -> None:
    """Keep the local preview readable while the realtime sync transaction writes."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    is_sqlite = settings.database_url.startswith("sqlite")
    connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}
    engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
    if is_sqlite:
        event.listen(engine, "connect", _configure_sqlite_connection)
    return engine


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with get_session_factory()() as session:
        yield session
