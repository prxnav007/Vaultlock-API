"""The migration must apply to an empty database and reverse cleanly.

The rest of the suite builds its schema from `Base.metadata`, which is fast and
which `alembic check` proves equivalent to the migrations. This test exercises
the migration scripts themselves, against a throwaway database, because a
metadata-equivalent migration can still fail to *run* -- the enum types are the
classic case: `create_table` creates them implicitly but `drop_table` leaves
them behind, so a downgrade followed by an upgrade fails on "type already
exists" unless the downgrade drops them explicitly.
"""
from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, make_url, text

from app.core.config import settings
from tests.conftest import create_test_database

pytestmark = pytest.mark.db

SCRATCH_SUFFIX = "_migration"
EXPECTED_TABLES = {"merchants", "payments", "idempotency_records", "alembic_version"}
EXPECTED_ENUMS = {"payment_status", "idempotency_state"}


@pytest.fixture
def scratch_url() -> str:
    """A database used only by this test, dropped afterwards."""
    url = make_url(settings.sync_database_url)
    scratch = url.set(database=f"{url.database}{SCRATCH_SUFFIX}")
    rendered = scratch.render_as_string(hide_password=False)
    try:
        drop_database(rendered)
        create_test_database(rendered)
    except Exception as exc:  # pragma: no cover - environment problem
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}: {exc}")
    try:
        yield rendered
    finally:
        drop_database(rendered)


def drop_database(url: str) -> None:
    target = make_url(url)
    admin = create_engine(
        target.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    try:
        with admin.connect() as conn:
            conn.execute(
                text(f'DROP DATABASE IF EXISTS "{target.database}" WITH (FORCE)')
            )
    finally:
        admin.dispose()


def alembic_config(url: str) -> Config:
    """Point Alembic at the scratch database.

    `alembic/env.py` reads the URL from settings, so the setting is what has to
    be redirected.
    """
    config = Config("alembic.ini")
    target = make_url(url)
    settings.POSTGRES_DB = target.database
    return config


def enum_labels(engine) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text("SELECT typname FROM pg_type WHERE typtype = 'e'")
            ).scalars()
        )


def test_migration_applies_then_reverses_then_reapplies(scratch_url: str) -> None:
    original_db = settings.POSTGRES_DB
    engine = create_engine(scratch_url)
    try:
        config = alembic_config(scratch_url)

        command.upgrade(config, "head")
        assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
        assert EXPECTED_ENUMS <= enum_labels(engine)

        command.downgrade(config, "base")
        remaining = set(inspect(engine).get_table_names())
        assert not (EXPECTED_TABLES - {"alembic_version"}) & remaining
        # The enum types must go too, or the next upgrade fails.
        assert not EXPECTED_ENUMS & enum_labels(engine)

        # The cycle that catches a downgrade which only half-cleans up.
        command.upgrade(config, "head")
        assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    finally:
        settings.POSTGRES_DB = original_db
        engine.dispose()
