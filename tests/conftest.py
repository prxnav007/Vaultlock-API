"""Shared fixtures.

Database tests run against a DEDICATED test database, never the one the ML
pipeline populates -- the generator truncates its tables, and a suite that
shared them could destroy a dataset that takes minutes to rebuild. The test
database name comes from TEST_DATABASE_URL, or defaults to the configured
database with a `_test` suffix; it is created on demand.
"""
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import Base
from app.db.models import Merchant


def test_database_url() -> str:
    override = os.getenv("TEST_DATABASE_URL")
    if override:
        return override
    url = make_url(settings.sync_database_url)
    return url.set(database=f"{url.database}_test").render_as_string(
        hide_password=False
    )


def create_test_database(url: str) -> None:
    """Create the test database if it does not exist yet."""
    target = make_url(url)
    admin = create_engine(
        target.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def engine():
    """An engine on the test database, with the schema applied.

    The schema is built from `Base.metadata`, which `alembic check` proves is
    identical to the migrations -- so this stays faithful without making every
    test run pay for a migration cycle.
    """
    url = test_database_url()
    try:
        create_test_database(url)
    except Exception as exc:  # pragma: no cover - environment problem
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}: {exc}")

    test_engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(test_engine)
    try:
        yield test_engine
    finally:
        test_engine.dispose()


@pytest.fixture
def db_session(engine) -> Iterator[Session]:
    """A session in a transaction that is always rolled back."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        # A test that asserts on IntegrityError has already caused an implicit
        # rollback, which deassociates the transaction from the connection.
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def merchant(db_session: Session) -> Merchant:
    """One persisted merchant with a year of tenure."""
    record = Merchant(
        merchant_id=uuid.uuid4(),
        joined_at=datetime.now(UTC) - timedelta(days=365),
        industry="retail",
    )
    db_session.add(record)
    db_session.flush()
    return record
