"""The schema invariants spec Milestone 1 requires.

Every test here asserts a guarantee the ML pipeline then relies on: a payment
always belongs to a real merchant, an amount is always positive and always in
minor units, and a status is always one of three known labels.
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    IdempotencyRecord,
    IdempotencyState,
    Merchant,
    Payment,
    PaymentStatus,
)

pytestmark = pytest.mark.db


def make_payment(merchant_id: uuid.UUID, **overrides) -> Payment:
    fields = {
        "payment_id": uuid.uuid4(),
        "merchant_id": merchant_id,
        "amount_minor": 52950,
        "currency": "INR",
        "status": PaymentStatus.SUCCESS,
        "created_at": datetime.now(UTC),
        "processed_at": datetime.now(UTC),
    }
    fields.update(overrides)
    return Payment(**fields)


def test_merchant_inserts_and_reads_back(db_session: Session) -> None:
    joined = datetime.now(UTC) - timedelta(days=400)
    record = Merchant(merchant_id=uuid.uuid4(), joined_at=joined, industry="travel")
    db_session.add(record)
    db_session.flush()

    stored = db_session.get(Merchant, record.merchant_id)
    assert stored is not None
    assert stored.industry == "travel"
    # created_at comes from the server default, so it is set without being passed.
    assert stored.created_at is not None


def test_merchant_id_defaults_to_a_server_generated_uuid(db_session: Session) -> None:
    record = Merchant(joined_at=datetime.now(UTC))
    db_session.add(record)
    db_session.flush()
    assert isinstance(record.merchant_id, uuid.UUID)


def test_payment_requires_an_existing_merchant(db_session: Session) -> None:
    db_session.add(make_payment(uuid.uuid4()))
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize("amount", [0, -1, -52950])
def test_nonpositive_amount_is_rejected(
    db_session: Session, merchant: Merchant, amount: int
) -> None:
    db_session.add(make_payment(merchant.merchant_id, amount_minor=amount))
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize("currency", ["IN", "INRX"])
def test_currency_must_be_exactly_three_characters(
    db_session: Session, merchant: Merchant, currency: str
) -> None:
    db_session.add(make_payment(merchant.merchant_id, currency=currency))
    # Two chars trips the check constraint; four trips the varchar(3) length.
    with pytest.raises((IntegrityError, DataError)):
        db_session.flush()


def test_payment_status_rejects_an_unknown_label(
    db_session: Session, merchant: Merchant
) -> None:
    with pytest.raises(Exception):
        db_session.execute(
            text(
                "INSERT INTO payments "
                "(payment_id, merchant_id, amount_minor, currency, status) "
                "VALUES (:pid, :mid, 100, 'INR', 'REFUNDED')"
            ),
            {"pid": uuid.uuid4(), "mid": merchant.merchant_id},
        )


def test_duplicate_merchant_and_idempotency_key_cannot_commit(
    db_session: Session, merchant: Merchant
) -> None:
    for _ in range(2):
        db_session.add(
            IdempotencyRecord(
                id=uuid.uuid4(),
                merchant_id=merchant.merchant_id,
                idempotency_key="550e8400-e29b-41d4-a716-446655440000",
                request_fingerprint="a" * 64,
                state=IdempotencyState.PROCESSING,
            )
        )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_same_idempotency_key_is_allowed_for_a_different_merchant(
    db_session: Session, merchant: Merchant
) -> None:
    other = Merchant(merchant_id=uuid.uuid4(), joined_at=datetime.now(UTC))
    db_session.add(other)
    db_session.flush()

    key = "550e8400-e29b-41d4-a716-446655440000"
    for owner in (merchant.merchant_id, other.merchant_id):
        db_session.add(
            IdempotencyRecord(
                id=uuid.uuid4(),
                merchant_id=owner,
                idempotency_key=key,
                request_fingerprint="b" * 64,
                state=IdempotencyState.PROCESSING,
            )
        )
    db_session.flush()  # keys are merchant-scoped, so this is legitimate


def test_analytical_index_exists(db_session: Session) -> None:
    """The feature pipeline's only hot query is (merchant_id, created_at)."""
    found = db_session.execute(
        text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
        {"name": "ix_payments_merchant_id_created_at"},
    ).scalar_one()
    assert "merchant_id" in found and "created_at" in found
