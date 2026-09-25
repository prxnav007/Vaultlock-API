from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes import health
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        # Fail fast, without echoing the driver error (it carries the host
        # and user).
        raise RuntimeError(
            "Startup failed: could not connect to PostgreSQL. "
            "Check that the database is running and that the POSTGRES_* "
            "settings are correct."
        ) from None

    yield

    await engine.dispose()


app = FastAPI(title="vault-api", lifespan=lifespan)
app.include_router(health.router)
