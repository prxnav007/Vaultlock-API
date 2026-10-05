"""Load a simulated history into PostgreSQL.

Kept apart from `ml.synthetic.generate` so that generation is provably pure:
the generator module imports nothing from `app`, so its reproducibility tests
cannot touch a database even by accident.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import insert, text

from app.db.models import Merchant
from app.db.sync_session import sync_engine
from ml.synthetic.generate import CURRENCY, MerchantProfile, PaymentBatch

COPY_PAYMENTS = (
    "COPY payments "
    "(payment_id, merchant_id, amount_minor, currency, status, failure_code, "
    "created_at, processed_at, updated_at) FROM STDIN"
)


def truncate_tables() -> None:
    """Empty the ledger. TRUNCATE, never DROP -- the schema is Alembic's."""
    with sync_engine.begin() as conn:
        conn.execute(text("TRUNCATE payments, idempotency_records, merchants CASCADE"))


def write_merchants(profiles: list[MerchantProfile], start: datetime) -> None:
    rows = [
        {
            "merchant_id": p.merchant_id,
            "joined_at": start + timedelta(days=int(p.join_day)),
            "industry": p.industry,
        }
        for p in profiles
    ]
    with sync_engine.begin() as conn:
        conn.execute(insert(Merchant), rows)


def copy_payments(
    profiles: list[MerchantProfile],
    batches: list[PaymentBatch],
    chunk_merchants: int = 250,
) -> int:
    """Bulk-load the ledger with COPY in text format.

    Text rather than binary because `status` is a native Postgres enum: the
    server parses the label itself, so the client never has to register the
    type's runtime OID. At roughly 100k rows/s this is not the slow part.

    `sync_engine.begin()` commits each chunk on exit, so a failure part-way
    leaves whole merchants loaded rather than a half-written COPY stream.
    """
    written = 0
    for begin in range(0, len(profiles), chunk_merchants):
        window = slice(begin, begin + chunk_merchants)
        with sync_engine.begin() as conn:
            raw = conn.connection.driver_connection
            with raw.cursor() as cur, cur.copy(COPY_PAYMENTS) as copy:
                for profile, batch in zip(
                    profiles[window], batches[window], strict=True
                ):
                    merchant = str(profile.merchant_id)
                    stamps = np.datetime_as_string(batch.created_at, unit="us")
                    for i in range(len(batch)):
                        when = stamps[i]
                        copy.write_row(
                            (
                                str(batch.payment_id[i]),
                                merchant,
                                int(batch.amount_minor[i]),
                                CURRENCY,
                                str(batch.status[i]),
                                batch.failure_code[i],
                                when,
                                when,
                                when,
                            )
                        )
                        written += 1
        print(f"  copied {written:,} payments", file=sys.stderr)
    return written


def analyze() -> None:
    """Refresh planner statistics so the feature pipeline's reads use the index."""
    with sync_engine.begin() as conn:
        conn.execute(text("ANALYZE payments"))
        conn.execute(text("ANALYZE merchants"))
