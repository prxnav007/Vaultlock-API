"""HTTP contracts for merchants.

Response models only in this phase: synthetic history is seeded by script, so
there is no write path to validate yet.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MerchantResponse(BaseModel):
    """Merchant metadata as the API exposes it.

    Carries no derived state -- no churn flag, no RFM values, no last
    transaction time. Those are functions of the ledger and of the moment they
    are asked about, so they belong to the churn-risk endpoint, not here.
    """

    model_config = ConfigDict(from_attributes=True)

    merchant_id: uuid.UUID
    joined_at: datetime
    industry: str | None
    created_at: datetime
