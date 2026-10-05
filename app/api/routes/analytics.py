"""Churn-risk endpoint.

Exists only because the offline pipeline works: the model is trained, evaluated
and frozen elsewhere, and this route loads the result and applies it.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.analytics import ChurnRiskResponse
from app.services import churn_service
from ml.inference import ChurnModel

router = APIRouter(tags=["analytics"])


def get_churn_model(request: Request) -> ChurnModel:
    """The model loaded at startup.

    Returning 503 rather than scoring with an untrained fallback: a plausible
    number with no model behind it is worse than an honest refusal.
    """
    model = getattr(request.app.state, "churn_model", None)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="churn model is not loaded",
        )
    return model


@router.get(
    "/merchants/{merchant_id}/churn-risk",
    response_model=ChurnRiskResponse,
    responses={
        404: {"description": "Unknown merchant"},
        409: {"description": "Insufficient history to score this merchant"},
        503: {"description": "Model artifact not loaded"},
    },
)
async def read_churn_risk(
    merchant_id: uuid.UUID,
    as_of: datetime | None = Query(
        default=None,
        description=(
            "Score the merchant as at this instant. Defaults to the most recent "
            "payment in the ledger rather than the current time, so a fixed "
            "history is scored at the end of its own timeline."
        ),
    ),
    session: AsyncSession = Depends(get_session),
    model: ChurnModel = Depends(get_churn_model),
) -> ChurnRiskResponse:
    try:
        return await churn_service.churn_risk(session, model, merchant_id, as_of)
    except churn_service.MerchantNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="merchant not found"
        ) from None
    except churn_service.InsufficientHistory as exc:
        # A conflict with the resource's state, not a malformed request: the
        # call is well-formed and this merchant simply cannot be scored yet.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "insufficient_history", "reason": exc.reason},
        ) from None
