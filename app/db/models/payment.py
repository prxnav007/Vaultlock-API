import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PaymentStatus(enum.StrEnum):
    """Terminal state of a logical payment attempt.

    For ML, SUCCESS and FAILED both count as merchant activity: a merchant
    whose payments keep failing is experiencing friction, not absence.
    PENDING should not survive in historical data.

    StrEnum so `str(status)` is the bare label, which is what the generator's
    COPY stream and JSON serialization both need.
    """

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Payment(Base):
    """One logical payment attempt by a merchant -- not one HTTP request.

    A retried request carrying the same valid idempotency key resolves to this
    same row rather than creating another one, which is what keeps the ledger
    a record of merchant behaviour instead of a record of network noise.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="amount_minor_positive"),
        CheckConstraint("char_length(currency) = 3", name="currency_length"),
        # The dominant analytical query: one merchant's payments in a time
        # range. Every feature window is exactly that query.
        Index("ix_payments_merchant_id_created_at", "merchant_id", "created_at"),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchants.merchant_id"),
        nullable=False,
    )
    # Smallest currency unit. Never a float: 529.50 INR is 52950.
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        # values_callable so Postgres stores the member *values*. The default
        # stores member names; they match here, but relying on that is a trap.
        Enum(
            PaymentStatus,
            name="payment_status",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    failure_code: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
