"""Merchant reads."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Merchant


async def get_merchant(session: AsyncSession, merchant_id: uuid.UUID) -> Merchant | None:
    result = await session.execute(
        select(Merchant).where(Merchant.merchant_id == merchant_id)
    )
    return result.scalar_one_or_none()
