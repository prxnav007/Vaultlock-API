"""HTTP contract for the churn-risk endpoint.

The client sends no features. A caller that had to supply `recency_days` and
`frequency_change` would be reimplementing the feature pipeline against a
ledger it does not own, and any disagreement would silently change the score.
The service owns the ledger, so the service derives the features.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Direction = Literal["increases_risk", "decreases_risk"]
RiskBand = Literal["LOW", "MEDIUM", "HIGH"]


class TopFactor(BaseModel):
    """One feature's direction of effect on this merchant's score.

    A small number of named factors rather than the whole SHAP vector: the
    point is an explanation someone can act on, and a direction is honest about
    what SHAP shows. It describes how the feature moved the model's output, not
    that the feature caused the merchant to leave.
    """

    feature: str
    direction: Direction


class ChurnRiskResponse(BaseModel):
    merchant_id: uuid.UUID
    # The exact cut-off used to build the features, so the answer is auditable
    # rather than merely timestamped.
    snapshot_at: datetime
    churn_score: float = Field(ge=0.0, le=1.0)
    risk_band: RiskBand
    predicted_churn: bool
    top_factors: list[TopFactor]
    model_version: str
