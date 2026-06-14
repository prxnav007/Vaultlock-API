import uuid
from sqlalchemy import String, Numeric, DateTime, func, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime


class Base(DeclarativeBase):
    pass

class Transaction(Base):
    __tablename__ = "transactions"

    # --- Core Identity ---
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4 #our transaction_id needs default set so SQLAlchemy generates it Python-side before the insert, not database-side,If it's currently server_default or has no default, SQLAlchemy lets Postgres generate it and then doesn't know what it is until it re-fetches.       
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255),    
        unique=True,       # enforces exactly-once at the DB level too
        nullable=False,
        index=True         # fast lookup on every incoming request
    )

    # --- Business Data ---
    merchant_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True         # ML queries will GROUP BY and filter on this constantly(creates a B Tree)
    )
    amount: Mapped[float] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        server_default="0.00"
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD"
    )
    

    # --- State Machine ---
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING"   # always starts as PENDING, your logic updates it
        
    )
    failure_reason: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True       # only populated if status = FAILED
    )

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True          # ML time-series queries will ORDER BY and range-filter this
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),  # auto-updates when row changes (PENDING → SUCCESS)
        nullable=True
    )
    timeout_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )