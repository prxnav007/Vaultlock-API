import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Merchant(Base):
    """One merchant account whose payment activity may later be analyzed.

    Deliberately stores no derived state: `is_churned`, `last_transaction_at`
    and every RFM value are functions of the payment ledger and of the time
    they are asked about, so they belong to feature generation, not here.
    """

    __tablename__ = "merchants"

    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # Required by the ML pipeline: tenure_days is measured from this, and it
    # is what separates a new merchant from a long-standing inactive one.
    # The API sets it to now(); synthetic seeding inserts historical values.
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    # Plausible merchant metadata, kept for later segmentation. Not a V1
    # model feature: the generator assigns industry itself, so using it would
    # risk an artificial shortcut.
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
