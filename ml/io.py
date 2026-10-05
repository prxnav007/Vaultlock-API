"""Reads for the offline pipeline.

The sync engine lives in `app.db.sync_session`; only the ML side's query
shapes belong here. The ordering in `read_payments` is load-bearing -- see its
docstring.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import Engine, text

from app.db.sync_session import sync_engine


def read_merchants(engine: Engine | None = None) -> pd.DataFrame:
    """Every merchant and the one column the features need from them."""
    query = "SELECT merchant_id, joined_at FROM merchants ORDER BY merchant_id"
    with (engine or sync_engine).connect() as conn:
        return pd.read_sql(text(query), conn)


def read_payments(engine: Engine | None = None) -> pd.DataFrame:
    """The whole ledger, ordered by merchant then time.

    The ORDER BY is not cosmetic: it lets the snapshot builder slice one
    contiguous block per merchant and hand zero-copy array views to the
    feature core, instead of filtering 1.1M rows once per merchant. It is also
    exactly the order of `ix_payments_merchant_id_created_at`.
    """
    query = (
        "SELECT merchant_id, created_at, amount_minor, status::text AS status "
        "FROM payments ORDER BY merchant_id, created_at"
    )
    with (engine or sync_engine).connect() as conn:
        return pd.read_sql(text(query), conn)


def latest_payment_time(engine: Engine | None = None) -> pd.Timestamp:
    """The end of observable history.

    Everything downstream dates from this rather than from the wall clock: the
    label needs 60 observable days after a snapshot, and "now" is well past
    the end of a fixed dataset.
    """
    with (engine or sync_engine).connect() as conn:
        value = conn.execute(text("SELECT max(created_at) FROM payments")).scalar_one()
    if value is None:
        raise RuntimeError("no payments in the database -- run ml.synthetic.generate")
    return pd.Timestamp(value).tz_convert("UTC")
