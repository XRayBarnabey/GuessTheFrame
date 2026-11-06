from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

# Test runs must not depend on a personal .env file.
# This key is only used by the automated test suite (temporary databases).
os.environ.setdefault("GTF_ENV", "test")
os.environ.setdefault("GTF_SETUP_TOKEN", "test-setup-token")
os.environ.setdefault(
    "GTF_ENCRYPTION_KEY",
    "VODZILn5B62BNBM2JAHc9fl--c1cFugrKqnNdmiFhA8=",
)

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.rate_limit import frame_limiter, login_limiter, setup_limiter
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiters():
    login_limiter._events.clear()
    setup_limiter._events.clear()
    frame_limiter._events.clear()
    yield


@pytest_asyncio.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    db_path = tmp_path / "test.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client

    app.dependency_overrides.clear()
