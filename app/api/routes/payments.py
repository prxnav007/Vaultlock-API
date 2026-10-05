"""Payment read endpoint."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.payment import PaymentResponse
from app.services import payment_service

router = APIRouter(tags=["payments"])


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
async def read_payment(
    payment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PaymentResponse:
    payment = await payment_service.get_payment(session, payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="payment not found"
        )
    return PaymentResponse.model_validate(payment)
