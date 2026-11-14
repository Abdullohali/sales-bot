"""Tests run on SQLite (aiosqlite) by default.
Set TEST_DATABASE_URL=postgresql+asyncpg://... to run the same suite on PostgreSQL."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ.setdefault("BOT_TOKEN", "")
os.environ.setdefault("ADMIN_IDS", "1000")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("VAT_RATE", "12")
os.environ.setdefault("COMPANY_NAME", "ООО Тест")
os.environ.setdefault("COMPANY_INN", "123456789")

import pytest  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.models import Base  # noqa: E402

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite://")


@pytest.fixture
async def engine():
    kwargs = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}} if "sqlite" in TEST_DB_URL else {}
    eng = create_async_engine(TEST_DB_URL, **kwargs)
    if "sqlite" in TEST_DB_URL:
        # SQLite's built-in lower() is ASCII-only; PostgreSQL handles Cyrillic natively.
        @event.listens_for(eng.sync_engine, "connect")
        def _unicode_lower(dbapi_conn, _):
            dbapi_conn.create_function("lower", 1, lambda s: s.lower() if isinstance(s, str) else s)

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def session_maker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def session(session_maker):
    async with session_maker() as s:
        yield s
