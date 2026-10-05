"""Merchant read endpoint."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.merchant import MerchantResponse
from app.services import merchant_service

router = APIRouter(tags=["merchants"])


@router.get("/merchants/{merchant_id}", response_model=MerchantResponse)
async def read_merchant(
    merchant_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> MerchantResponse:
    merchant = await merchant_service.get_merchant(session, merchant_id)
    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="merchant not found"
        )
    return MerchantResponse.model_validate(merchant)
