from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.config import get_settings

_url = get_settings().DATABASE_URL
engine: AsyncEngine = create_async_engine(_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

if _url.startswith("sqlite"):  # local dev only; production uses PostgreSQL

    @event.listens_for(engine.sync_engine, "connect")
    def _unicode_lower(dbapi_conn, _):
        # SQLite's built-in lower() is ASCII-only -> Cyrillic name lookups would fail.
        dbapi_conn.create_function("lower", 1, lambda s: s.lower() if isinstance(s, str) else s)
