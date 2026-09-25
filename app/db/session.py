from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# One engine for the whole process. pool_pre_ping discards connections that
# the database dropped while they sat idle in the pool.
engine = create_async_engine(
    settings.async_database_url,
    pool_pre_ping=True,
)

# expire_on_commit=False so ORM objects stay usable after a commit, which
# matters when a service commits and then serializes the result.
SessionFactory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one fresh session per request.

    Deliberately does not commit or roll back: services own transaction
    boundaries explicitly via `async with session.begin()`.
    """
    session = SessionFactory()
    try:
        yield session
    finally:
        await session.close()
