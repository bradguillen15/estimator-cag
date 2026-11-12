"""Engine and session factory builders. Nothing is created at import time.

Two stacks coexist on purpose, both configured by the same ``DATABASE_URL``:

* **Sync (psycopg)**: Alembic and the session 6 repositories (ingestion jobs, pseudonym mappings), which run
  in background tasks or scripts, off the request path.
* **Async (asyncpg)**: the session 8 vector store (``POST /embeddings/ingest`` and ``POST /search``), which is
  on the request path, so Postgres I/O never blocks the event loop. Its URL swaps the driver token.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker


def build_engine(database_url: str) -> Engine:
    """Create an engine; SQLAlchemy connects lazily on first use."""
    return create_engine(database_url, pool_pre_ping=True)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def async_database_url(database_url: str) -> str:
    """The asyncpg flavour of ``database_url`` (a URL that already names asyncpg is returned as is)."""
    if "+psycopg" in database_url:
        return database_url.replace("+psycopg", "+asyncpg", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


def build_async_engine(database_url: str) -> AsyncEngine:
    """Async engine on asyncpg; like the sync one, it connects lazily."""
    return create_async_engine(async_database_url(database_url), pool_pre_ping=True)


def build_async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """``expire_on_commit=False`` keeps ORM objects (e.g. a new document id) readable after the commit."""
    return async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
