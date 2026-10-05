import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IdempotencyState(enum.StrEnum):
    """Lifecycle of one deduplicated request."""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"


class IdempotencyRecord(Base):
    """Maps merchant + idempotency key + request payload to one stored outcome.

    Kept out of `payments` so the ledger stays free of transport semantics.
    Nothing writes to this table yet -- the request-deduplication path is a
    later milestone -- but the schema is finished here so the core domain is
    defined in one migration.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (
        # Idempotency keys are merchant-scoped.
        UniqueConstraint(
            "merchant_id",
            "idempotency_key",
            name="uq_idempotency_records_merchant_id_idempotency_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchants.merchant_id"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    # SHA-256 over the canonical request semantics. The key alone is not
    # enough: the same key with a different amount must be rejected, not
    # replayed.
    request_fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    state: Mapped[IdempotencyState] = mapped_column(
        Enum(
            IdempotencyState,
            name="idempotency_state",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.payment_id"),
        nullable=True,
    )
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
