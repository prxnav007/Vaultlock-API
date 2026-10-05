"""HTTP contracts for payments."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models.payment import PaymentStatus


class PaymentResponse(BaseModel):
    """One logical payment's final state.

    `amount_minor` stays in the smallest currency unit all the way out to the
    client: converting to a decimal here would reintroduce the float rounding
    the schema exists to avoid.
    """

    model_config = ConfigDict(from_attributes=True)

    payment_id: uuid.UUID
    merchant_id: uuid.UUID
    amount_minor: int
    currency: str
    status: PaymentStatus
    failure_code: str | None
    created_at: datetime
    processed_at: datetime | None
    updated_at: datetime
